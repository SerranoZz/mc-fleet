import subprocess
import json
import csv
import os
import sys
import yaml
import argparse
from typing import Dict, Any, List, Optional

AZURE_CSV_FILE = "./csv_results/azure_vms_eastus.csv"
YAML_FILE = "./config/vm_catalog.yaml"
OUTPUT_DIR = "./csv_results"
os.makedirs(OUTPUT_DIR, exist_ok=True)

AWS_FAMILY_MAP = {
    'm': 'General Purpose', 't': 'General Purpose', 'a': 'General Purpose', 'c': 'Compute Optimized',
    'r': 'Memory Optimized', 'x': 'Memory Optimized', 'z': 'Memory Optimized', 'i': 'Storage Optimized',
    'd': 'Storage Optimized', 'h': 'Storage Optimized', 'p': 'Accelerated Computing', 'g': 'Accelerated Computing',
    'inf': 'Accelerated Computing', 'f': 'Accelerated Computing', 'hpc': 'HPC'
}
AZURE_FAMILY_MAP = {
    'D': 'General Purpose', 'B': 'General Purpose', 'A': 'General Purpose', 'F': 'Compute Optimized',
    'E': 'Memory Optimized', 'M': 'Memory Optimized', 'L': 'Storage Optimized', 'N': 'GPU', 'H': 'HPC'
}

def get_aws_family_purpose(instance_type: str) -> str:
    family_letter = instance_type.split('.')[0][0]
    return AWS_FAMILY_MAP.get(family_letter, "Unknown")

def get_azure_family_purpose(sku_name: str) -> str:
    try:
        family_letter = sku_name.split('_')[1][0]
        return AZURE_FAMILY_MAP.get(family_letter, "Unknown")
    except IndexError:
        return "Unknown"

def load_azure_vms_from_csv(csv_path: str) -> List[Dict[str, Any]]:
    print(f"🔄 Carregando catálogo de VMs da Azure do arquivo: {csv_path}", file=sys.stderr)
    azure_vms = []
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    azure_vms.append({
                        "type": row["VM_Size"], "vcpus": int(row["vCPUs"]), "memory": int(row["Memory_MB"]),
                        "architecture": row["Architecture"], "manufacturer": get_azure_cpu_manufacturer(row["VM_Size"]),
                        "family": get_azure_family_purpose(row["VM_Size"]), "spot_price": row["Spot_Price_USD"],
                        "spot_sku_name": row["Spot_SKU_Name"]
                    })
                except (ValueError, KeyError): continue
    except FileNotFoundError:
        print(f"ERRO CRÍTICO: Arquivo de catálogo da Azure não encontrado: '{csv_path}'", file=sys.stderr)
        sys.exit(1)
    print(f"✅ Catálogo da Azure carregado com {len(azure_vms)} instâncias.", file=sys.stderr)
    return azure_vms

def get_azure_cpu_manufacturer(sku_name: str) -> str:
    parts = sku_name.lower().split('_')
    if len(parts) > 1:
        size_part = parts[1]
        if 'a' in size_part: return "AMD"
        if 'p' in size_part: return "ARM"
    return "Intel"

def get_aws_cpu_manufacturer(instance_type: str, processor_info: Dict) -> str:
    if 'g' in instance_type.split('.')[0] or 'Arm64' in processor_info.get("SupportedArchitectures", []): return "ARM"
    if 'a' in instance_type.split('.')[0]: return "AMD"
    return "Intel"

def get_aws_instance_details(region: str, instance_names: List[str]) -> List[Dict[str, Any]]:
    print(f"🔄 Consultando especificações de {len(instance_names)} tipos de instância na AWS ({region})...", file=sys.stderr)
    aws_cmd = ["aws", "ec2", "describe-instance-types", "--region", region, "--instance-types"] + instance_names + ["--query", "InstanceTypes[*].{type:InstanceType, vcpus:VCpuInfo.DefaultVCpus, memory:MemoryInfo.SizeInMiB, processor:ProcessorInfo}"]
    try:
        aws_output = subprocess.check_output(aws_cmd, text=True, stderr=subprocess.PIPE)
        aws_instances_raw = json.loads(aws_output)
        
        processed_instances = []
        for inst in aws_instances_raw:
            inst['manufacturer'] = get_aws_cpu_manufacturer(inst['type'], inst.get('processor', {}))
            inst['family'] = get_aws_family_purpose(inst['type'])
            processed_instances.append(inst)
        return processed_instances
    except subprocess.CalledProcessError as e:
        print(f"ERRO: Falha ao chamar a AWS CLI. Verifique suas credenciais e a região '{region}'.", file=sys.stderr)
        return []

def find_best_azure_match(aws_instance: Dict[str, Any], available_azure_vms: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    aws_vcpus = aws_instance['vcpus']
    aws_memory = aws_instance['memory']
    aws_manufacturer = aws_instance['manufacturer']
    aws_family = aws_instance['family']
    
    candidates = []
    for i, az_vm in enumerate(available_azure_vms):
        if az_vm['vcpus'] != aws_vcpus: continue
        if az_vm['manufacturer'] != aws_manufacturer: continue
        if az_vm['memory'] < aws_memory: continue
        
        az_vm['index'] = i
        candidates.append(az_vm)

    if not candidates: return None

    candidates.sort(key=lambda az_vm: (az_vm['memory'] - aws_memory, 0 if az_vm['family'] == aws_family else 1))
    return candidates[0]

# ==============================================================================
# Lógica Principal (Modificada para aceitar o arquivo de exclusão)
# ==============================================================================
def main(aws_region_to_process: str, exclusion_file: Optional[str]):
    azure_vms_full_catalog = load_azure_vms_from_csv(AZURE_CSV_FILE)

    # --- NOVA LÓGICA DE EXCLUSÃO ---
    if exclusion_file:
        print(f"🔵 Aplicando exclusão com base no arquivo: {exclusion_file}", file=sys.stderr)
        try:
            with open(exclusion_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                # Cria um set para busca rápida das SKUs já usadas
                used_azure_skus = {row['Azure_Equivalent_Type'] for row in reader if row.get('Azure_Equivalent_Type') and row['Azure_Equivalent_Type'] != 'N/A'}
            
            initial_count = len(azure_vms_full_catalog)
            # Filtra o catálogo, mantendo apenas as VMs que NÃO foram usadas
            azure_vms = [vm for vm in azure_vms_full_catalog if vm['type'] not in used_azure_skus]
            final_count = len(azure_vms)
            
            print(f"✅ {initial_count - final_count} SKUs da Azure foram excluídas. {final_count} SKUs permanecem disponíveis para mapeamento.", file=sys.stderr)

        except FileNotFoundError:
            print(f"ERRO: Arquivo de exclusão não encontrado: '{exclusion_file}'", file=sys.stderr)
            sys.exit(1)
    else:
        # Se nenhum arquivo de exclusão for fornecido, usa o catálogo completo
        azure_vms = azure_vms_full_catalog

    # O resto do script continua a partir daqui usando a lista 'azure_vms' (completa ou filtrada)
    with open(YAML_FILE, "r") as f:
        config_data = yaml.safe_load(f)

    print(f"\n{'='*20} MAPEANDO REGIÃO AWS: {aws_region_to_process.upper()} {'='*20}", file=sys.stderr)
    
    region_data = config_data.get("providers", {}).get("aws", {}).get("regions", {}).get(aws_region_to_process)
    if not region_data:
        print(f"ERRO: Região '{aws_region_to_process}' não encontrada no arquivo {YAML_FILE}", file=sys.stderr)
        sys.exit(1)

    raw_instance_types = region_data.get("instance_types", [])
    all_instance_names = []
    for item in raw_instance_types:
        if isinstance(item, list):
            for sub_item in item: all_instance_names.append(sub_item["name"])
        elif isinstance(item, dict):
            all_instance_names.append(item["name"])
    
    aws_instance_names_x64 = [name for name in all_instance_names if 'g' not in name.split('.')[0]]
    print(f"Encontradas {len(all_instance_names)} instâncias no YAML. Mantendo {len(aws_instance_names_x64)} instâncias x64 para processar.", file=sys.stderr)

    if not aws_instance_names_x64: return
    aws_instances = get_aws_instance_details(aws_region_to_process, aws_instance_names_x64)
    if not aws_instances: return

    available_azure = azure_vms.copy()
    matches = []
    aws_instances.sort(key=lambda x: (x["vcpus"], x["memory"]), reverse=True)

    for aws in aws_instances:
        best_azure_match = find_best_azure_match(aws, available_azure)
        if best_azure_match:
            available_azure.pop(best_azure_match['index'])

        matches.append({
            "AWS_Type": aws["type"], "AWS_Family": aws["family"], "AWS_vCPUs": aws["vcpus"], "AWS_Memory_MB": aws["memory"], "AWS_CPU": aws["manufacturer"],
            "Azure_Equivalent_Type": best_azure_match["type"] if best_azure_match else "N/A",
            "Azure_Family": best_azure_match["family"] if best_azure_match else "N/A",
            "Azure_vCPUs": best_azure_match["vcpus"] if best_azure_match else "N/A",
            "Azure_Memory_MB": best_azure_match["memory"] if best_azure_match else "N/A",
            "Azure_CPU": best_azure_match["manufacturer"] if best_azure_match else "N/A",
            "Azure_Spot_Price": best_azure_match["spot_price"] if best_azure_match else "N/A",
            "Azure_Spot_SKU_Name": best_azure_match["spot_sku_name"] if best_azure_match else "N/A",
        })

    matches.sort(key=lambda x: (x["AWS_vCPUs"], x["AWS_Memory_MB"]))

    # Adiciona um sufixo ao nome do arquivo se a exclusão foi aplicada
    file_suffix = "_exclusive" if exclusion_file else ""
    csv_file = os.path.join(OUTPUT_DIR, f"aws_to_azure_{aws_region_to_process}_mapping{file_suffix}.csv")
    
    with open(csv_file, "w", newline="", encoding='utf-8') as f:
        if not matches:
            print("Nenhuma correspondência encontrada para gerar o CSV.", file=sys.stderr)
            return
        writer = csv.DictWriter(f, fieldnames=matches[0].keys())
        writer.writeheader()
        writer.writerows(matches)

    print(f"✅ Mapeamento concluído. CSV gerado: {csv_file}", file=sys.stderr)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mapeia instâncias AWS para Azure com base na finalidade, CPU e especificações.")
    parser.add_argument("--aws-region", required=True, type=str, help="A região da AWS para processar (ex: sa-east-1).")
    parser.add_argument(
        "--exclude-from",
        type=str,
        help="Caminho para um CSV de mapeamento anterior. As SKUs da Azure usadas nesse arquivo serão excluídas da busca."
    )
    args = parser.parse_args()
    main(args.aws_region, args.exclude_from)