from flask import Flask, request, jsonify
import libvirt
import sys

app = Flask(__name__)

# Connect to the local KVM hypervisor
def get_libvirt_connection():
    try:
        conn = libvirt.open('qemu:///system')
        return conn
    except libvirt.libvirtError as e:
        print(f"Failed to connect to libvirt: {e}")
        return None

# Dummy VM flavors and images (replace with your own)
FLAVORS = {
    "small": {"cpu": 1, "ram": 1024},  # 1 vCPU, 1GB RAM
    "medium": {"cpu": 2, "ram": 2048}  # 2 vCPUs, 2GB RAM
}
IMAGES = ["ubuntu-20.04.qcow2", "centos-7.qcow2"]

@app.route('/')
def home():
    return app.send_static_file('index.html')

@app.route('/api/flavors', methods=['GET'])
def get_flavors():
    return jsonify(FLAVORS)

@app.route('/api/images', methods=['GET'])
def get_images():
    return jsonify(IMAGES)

@app.route('/api/create-vm', methods=['POST'])
def create_vm():
    data = request.get_json()
    flavor = data.get('flavor')
    image = data.get('image')
    vm_name = data.get('name', 'my-vm')

    if flavor not in FLAVORS or image not in IMAGES:
        return jsonify({"error": "Invalid flavor or image"}), 400

    # Connect to KVM
    conn = get_libvirt_connection()
    if not conn:
        return jsonify({"error": "Failed to connect to hypervisor"}), 500

    # Define VM XML (simplified example)
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
        # Create the VM
        vm = conn.defineXML(xml)
        vm.create()  # Start the VM
        return jsonify({"message": f"VM {vm_name} created successfully"}), 200
    except libvirt.libvirtError as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
