from flask import Flask, request, jsonify, render_template, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import libvirt
import smtplib
from email.mime.text import MIMEText
import os
from dotenv import load_dotenv
import pyotp  # For generating verification codes

app = Flask(__name__)
app.secret_key = 'your-secret-key'  # Replace with a secure random key
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
db = SQLAlchemy(app)

# Load environment variables for email
load_dotenv()
EMAIL_ADDRESS = os.getenv('EMAIL_ADDRESS')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# User model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    is_verified = db.Column(db.Boolean, default=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# KVM connection
def get_libvirt_connection():
    try:
        conn = libvirt.open('qemu:///system')
        return conn
    except libvirt.libvirtError as e:
        print(f"Failed to connect to libvirt: {e}")
        return None

# VM flavors and images
FLAVORS = {"small": {"cpu": 1, "ram": 1024}, "medium": {"cpu": 2, "ram": 2048}}
IMAGES = ["ubuntu-20.04.qcow2", "centos-7.qcow2"]

# Send verification email
def send_verification_email(email, code):
    msg = MIMEText(f"Your verification code is: {code}")
    msg['Subject'] = 'Verify Your Email - MyCloud'
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = email

    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False

# Routes
@app.route('/')
@login_required
def home():
    return app.send_static_file('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        if User.query.filter_by(email=email).first():
            flash('Email already registered.')
            return redirect(url_for('register'))
        
        user = User(email=email, password=password)  # In production, hash the password!
        db.session.add(user)
        db.session.commit()

        # Generate and send verification code
        code = pyotp.random_base32()[:6]  # 6-digit code
        if send_verification_email(email, code):
            flash('Verification code sent to your email.')
            return redirect(url_for('verify', email=email, code=code))
        else:
            flash('Failed to send verification email.')
            return redirect(url_for('register'))
    return render_template('register.html')

@app.route('/verify', methods=['GET', 'POST'])
def verify():
    email = request.args.get('email')
    expected_code = request.args.get('code')
    if request.method == 'POST':
        user_code = request.form['code']
        if user_code == expected_code:
            user = User.query.filter_by(email=email).first()
            user.is_verified = True
            db.session.commit()
            flash('Email verified! Please log in.')
            return redirect(url_for('login'))
        else:
            flash('Invalid code.')
    return render_template('verify.html', email=email)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and user.password == password and user.is_verified:  # In production, use password hashing!
            login_user(user)
            return redirect(url_for('home'))
        else:
            flash('Invalid credentials or unverified email.')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/api/flavors', methods=['GET'])
@login_required
def get_flavors():
    return jsonify(FLAVORS)

@app.route('/api/images', methods=['GET'])
@login_required
def get_images():
    return jsonify(IMAGES)

@app.route('/api/create-vm', methods=['POST'])
@login_required
def create_vm():
    data = request.get_json()
    flavor = data.get('flavor')
    image = data.get('image')
    vm_name = f"{current_user.email}-{data.get('name', 'my-vm')}"

    if flavor not in FLAVORS or image not in IMAGES:
        return jsonify({"error": "Invalid flavor or image"}), 400

    conn = get_libvirt_connection()
    if not conn:
        return jsonify({"error": "Failed to connect to hypervisor"}), 500

    xml = f"""
    <domain type='kvm'>
      <name>{vm_name}</name>
      <memory unit='MiB'>{FLAVORS[flavor]['ram']}</memory>
      <vcpu>{FLAVORS[flavor]['cpu']}</vcpu>
      <os>
        <type arch='x86_64'>hvm</type>
        <boot dev='hd'/>
      </os>
      <devices>
        <disk type='file' device='disk'>
          <driver name='qemu' type='qcow2'/>
          <source file='/var/lib/libvirt/images/{image}'/>
          <target dev='vda' bus='virtio'/>
        </disk>
        <interface type='network'>
          <source network='default'/>
        </interface>
      </devices>
    </domain>
    """

    try:
        vm = conn.defineXML(xml)
        vm.create()
        return jsonify({"message": f"VM {vm_name} created successfully"}), 200
    except libvirt.libvirtError as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

# Create database
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
