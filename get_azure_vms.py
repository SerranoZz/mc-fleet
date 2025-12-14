#!/usr/bin/env python3
import requests
import argparse
import sys
import csv
from datetime import datetime
import concurrent.futures
from typing import Tuple, Optional, Dict, Any
from azure.identity import DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.resource import SubscriptionClient

def get_azure_spot_linux_price(arm_region_name: str, arm_sku_name: str) -> Optional[Tuple[float, str]]:
    base_url = "https://prices.azure.com/api/retail/prices"
    filter_string = f"armRegionName eq '{arm_region_name}' and armSkuName eq '{arm_sku_name}'"
    params = {'$filter': filter_string}
    try:
        response = requests.get(base_url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        for item in data.get("Items", []):
            if 'Spot' in item.get('skuName', '') and 'Windows' not in item.get('productName', '') and item.get('type') == 'Consumption':
                return item.get('retailPrice'), item.get('skuName')
        return None
    except requests.exceptions.RequestException:
        return None

def parse_sku_capabilities(capabilities: list) -> Dict[str, Any]:
    specs = {'vCPUs': 'N/A', 'MemoryGB': 'N/A', 'CpuArchitecture': 'N/A'}
    for cap in capabilities:
        if cap.name == 'vCPUs': specs['vCPUs'] = cap.value
        elif cap.name == 'MemoryGB': specs['MemoryGB'] = cap.value
        elif cap.name == 'CpuArchitectureType': specs['CpuArchitecture'] = cap.value
    return specs

def fetch_price_for_sku(sku, location: str):
    vm_size = sku.name
    specs = parse_sku_capabilities(sku.capabilities)
    price_info = get_azure_spot_linux_price(location, vm_size)
    spot_price, spot_sku_name = price_info if price_info else ('N/A', 'N/A')
    
    memory_mb = 'N/A'
    try:
        memory_gb_float = float(specs['MemoryGB'])
        memory_mb = int(memory_gb_float * 1024)
    except (ValueError, TypeError):
        memory_mb = 'N/A'
        
    return (
        vm_size,
        specs['vCPUs'],
        memory_mb,
        specs['CpuArchitecture'],
        spot_price,
        spot_sku_name
    )

def list_large_vm_sizes_for_region(location: str, output_file: Optional[str] = None):
    VCPU_THRESHOLD = 2
    print(f"Buscando todos os tamanhos de VM com até {VCPU_THRESHOLD} vCPUs em '{location}'...", file=sys.stderr)

    if output_file is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"./csv_results/azure_vms_{location}.csv"

    try:
        credential = DefaultAzureCredential()
        subscription_id = next(SubscriptionClient(credential).subscriptions.list()).subscription_id
        compute_client = ComputeManagementClient(credential, subscription_id)
    except Exception as e:
        print(f"\nERRO: Falha na autenticação. Verifique seu login 'az login'. Detalhe: {e}", file=sys.stderr)
        return

    try:
        print("Passo 1: Obtendo a lista completa de tamanhos de VM...", file=sys.stderr)
        all_skus = list(compute_client.resource_skus.list(filter=f"location eq '{location}'"))

        large_vms_to_process = [
            sku for sku in all_skus 
            if sku.resource_type == "virtualMachines" and int(parse_sku_capabilities(sku.capabilities).get('vCPUs', 0)) <= VCPU_THRESHOLD and parse_sku_capabilities(sku.capabilities).get('CpuArchitecture', '0') == 'x64'
        ]
        
        if not large_vms_to_process:
            print(f"\nNenhum tamanho de VM com mais de {VCPU_THRESHOLD} vCPUs encontrado em '{location}'.", file=sys.stderr)
            return

        print(f"Passo 2: Encontrados {len(large_vms_to_process)} tamanhos de VM para processar.", file=sys.stderr)
        print(f"Passo 3: Iniciando busca de preços e salvando em '{output_file}'...", file=sys.stderr)
        
        # --- ALTERAÇÃO AQUI: Atualiza o nome da coluna no cabeçalho ---
        header = ["VM_Size", "vCPUs", "Memory_MB", "Architecture", "Spot_Price_USD", "Spot_SKU_Name"]
        
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            csv_writer = csv.writer(csvfile)
            csv_writer.writerow(header)

            with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
                future_to_sku = {executor.submit(fetch_price_for_sku, sku, location): sku.name for sku in large_vms_to_process}
                
                processed_count = 0
                for future in concurrent.futures.as_completed(future_to_sku):
                    try:
                        result_tuple = future.result()
                        csv_writer.writerow(result_tuple)
                        processed_count += 1
                        print(f"  ... {processed_count}/{len(large_vms_to_process)} processados.", end='\r', file=sys.stderr)
                    except Exception as exc:
                        vm_name = future_to_sku[future]
                        print(f"ERRO ao processar {vm_name}: {exc}", file=sys.stderr)
        
        print(f"\n\nProcesso concluído. Resultados salvos em: {output_file}", file=sys.stderr)

    except Exception as e:
        print(f"\nERRO geral ao listar as SKUs. A região '{location}' é válida? Detalhe: {e}", file=sys.stderr)
        return

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=f"Lista tamanhos de VM com mais de 96 vCPUs em uma região da Azure e salva em um arquivo CSV."
    )
    parser.add_argument(
        "-l", "--location",
        required=True,
        type=str,
        help="A região da Azure para consultar (ex: brazilsouth, eastus)."
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        help="Nome do arquivo CSV de saída. Se não for fornecido, um nome padrão será gerado."
    )
    args = parser.parse_args()

    list_large_vm_sizes_for_region(args.location, args.output)