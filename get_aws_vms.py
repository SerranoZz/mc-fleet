import subprocess
import csv
import json

REGIONS = ["sa-east-1", "us-east-1"]
OUTPUT_FILES = {
    "sa-east-1": "./csv_results/aws_vms_sa-east-1.csv",
    "us-east-1": "./csv_results/aws_vms_us-east-1.csv"
}

def get_instances(region):
    filters_json = json.dumps([
        {"Name": "vcpu-info.default-vcpus", "Values": ["2"]},
    ])
    cmd = [
        "aws", "ec2", "describe-instance-types",
        "--region", region,
        "--filters", filters_json,
        "--query", "InstanceTypes[].{InstanceType:InstanceType, vCPUs:VCpuInfo.DefaultVCpus, MemoryMiB:MemoryInfo.SizeInMiB, Network:NetworkInfo.NetworkPerformance, Architecture:ProcessorInfo.SupportedArchitectures}",
        "--output", "json"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)

instances_sa = get_instances("sa-east-1")
sa_types = set()  
with open(OUTPUT_FILES["sa-east-1"], "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["InstanceType", "vCPUs"])
    for inst in instances_sa:
        arch_val = inst.get("Architecture", [])
        arch_val = arch_val[0] if isinstance(arch_val, list) and arch_val else ""
        if arch_val == 'x86_64':
            writer.writerow([
                inst.get("InstanceType", ""),
                inst.get("vCPUs", ""),
            ])
            sa_types.add(inst.get("InstanceType", ""))

print(f"✅ CSV sa-east-1 salvo: {OUTPUT_FILES['sa-east-1']} ({len(sa_types)} instâncias)")

instances_us = get_instances("us-east-1")
with open(OUTPUT_FILES["us-east-1"], "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["InstanceType", "vCPUs"])
    count = 0
    for inst in instances_us:
        instance_type = inst.get("InstanceType", "")
        if instance_type in sa_types:
            continue  
        arch_val = inst.get("Architecture", [])
        arch_val = arch_val[0] if isinstance(arch_val, list) and arch_val else ""
        if arch_val == 'x86_64':
            writer.writerow([
                inst.get("InstanceType", ""),
                inst.get("vCPUs", ""),
            ])
        count += 1

print(f"✅ CSV us-east-1 salvo: {OUTPUT_FILES['us-east-1']} ({count} instâncias únicas)")
