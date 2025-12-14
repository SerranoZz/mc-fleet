import logging
import sys
import yaml
import time
from collections import defaultdict

from app.services.fleet_service import FleetService
from app.services.catalog_service import CatalogService
from app.provider_factory.factory import CloudProviderFactory
from app.clients.pricing_client import PricingClient

def run_single_test(test_params: dict):
    providers_to_run = test_params.get('providers')
    location = test_params.get('location')
    num_vcpus = test_params.get('vcpus')
    num_nodes = test_params.get('nodes')
    allocation_strategy = test_params.get('strategy')
    test_type = test_params.get('type')

    try:
        with open('./config/vm_catalog.yaml', 'r') as f:
            catalog_config = yaml.safe_load(f)
    except (FileNotFoundError, yaml.YAMLError) as e:
        logging.error(f"Erro ao carregar 'vm_catalog.yaml': {e}")
        return {
            "test_name": test_params.get('name'),
            "parameters": test_params,
            "status": "SETUP_FAILURE",
            "errors": [f"Falha ao carregar vm_catalog.yaml: {e}"]
        }

    
    available_providers = {name: CloudProviderFactory.get_provider(name) for name in providers_to_run}
    pricing_client = PricingClient()
    catalog_service = CatalogService(available_providers, pricing_client)
    fleet_service = FleetService(available_providers)

    final_fleets = {}
    all_errors = []
    status = "SUCCESS"

    provisioning_time = 0

    try:
        logging.info("Construindo catálogo de VMs...")
        is_multicloud_catalog = (test_type == 'multi_cloud')

        limit = 99999
        
        instance_options = catalog_service.build_catalog_in_parallel(catalog_config, num_vcpus, location, is_multicloud_catalog, limit)

        serializable_price_list = []
        if instance_options:
            if isinstance(instance_options[0], list):
                serializable_price_list = [[vm.to_dict() for vm in group] for group in instance_options]
            else:
                serializable_price_list = [vm.to_dict() for vm in instance_options]
        
        
        if not any(instance_options):
            raise RuntimeError("Nenhuma VM encontrada para os critérios especificados.")

        logging.info(f"Catálogo construído. Provisionando frota do tipo '{test_type}'...")

        start_time = time.time() 
        if test_type == 'single_cloud':
            final_fleets = fleet_service.provision_fleet_single_cloud(instance_options, num_nodes, allocation_strategy)
        elif test_type == 'multi_cloud':
            final_fleets = fleet_service.provision_fleet_multi_cloud(instance_options, num_nodes, allocation_strategy)
        else:
            raise ValueError(f"Tipo de teste desconhecido: '{test_type}'")
        end_time = time.time()
        provisioning_time = end_time - start_time
    except Exception as e:
        logging.error(f"Erro durante a execução do teste '{test_params.get('name')}': {e}", exc_info=True)
        all_errors.append(str(e))
        status = "EXECUTION_FAILURE"
    
    finally:
        logging.info("Iniciando limpeza de recursos (deleção de frotas)...")
        fleet_service.delete_fleet()
        logging.info("Limpeza de recursos concluída.")

    if all_errors and final_fleets:
        status = "PARTIAL_SUCCESS"
    elif all_errors and not final_fleets:
        status = "COMPLETE_FAILURE"
    

    processed_fleets = []
    for fleet_id, vms in final_fleets.items():
        summary_map = defaultdict(lambda: {"count": 0, "price_per_instance": 0.0, "provider": ""})
        for vm in vms:
            key = (vm.instance_type, vm.region_az)
            summary_map[key]["count"] += 1
            summary_map[key]["price_per_instance"] = vm.price
            summary_map[key]["provider"] = vm.provider

        summary_list = [
            {
                "instance_type": k[0],
                "region_az": k[1],
                "provider": v["provider"],
                "count": v["count"],
                "price_per_instance": v["price_per_instance"]
            }
            for k, v in summary_map.items()
        ]

        processed_fleets.append({
            "fleet_id": fleet_id,
            "total_vms": len(vms),
            "summary": summary_list,
        })
    
    result_data = {
        "test_name": test_params.get('name'),
        "parameters": test_params,
        "status": status,
        "provisioning_time_seconds": round(provisioning_time, 2),
        "pricing_catalog": serializable_price_list[:10],
        "fleets": processed_fleets,
        "errors": all_errors
    }

    return result_data
