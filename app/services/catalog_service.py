# app/services/catalog_service.py

import concurrent.futures
import logging
from ..core.models import VMSpec

class CatalogService:
    def __init__(self, providers, pricing_client):
        self.providers = providers
        self.pricing_client = pricing_client

    def _fetch_provider_prices(self, provider_name, provider_config, vcpus, location, limit):
        if provider_name== 'aws':
            limit = 99999
        provider_instance = self.providers.get(provider_name)
        if not provider_instance:
            logging.info(f"THREAD-{provider_name.upper()}: Provedor não encontrado. Pulando.")
            return []

        for region_name, region_data in provider_config['regions'].items():
            flat_instance_list = []
            for item in region_data['instance_types']:
                if isinstance(item, list):
                    flat_instance_list.extend(item)
                else:
                    flat_instance_list.append(item)
            region_data['instance_types'] = flat_instance_list
        
        candidates = provider_instance.get_all_vms(provider_config, vcpus, location)
        
        vms_with_prices = self.pricing_client.get_prices_for(candidates)

        return vms_with_prices


    def build_catalog_in_parallel(self, catalog_config, vcpus, location, group_by_price, limit):
        all_priced_vms = []
        
        # Usamos ThreadPoolExecutor para gerenciar as threads de forma segura
        with concurrent.futures.ThreadPoolExecutor() as executor:
            # Submetemos uma tarefa para cada provedor
            future_to_provider = {
                executor.submit(self._fetch_provider_prices, provider_name, provider_config, vcpus, location, limit): provider_name
                for provider_name, provider_config in catalog_config['providers'].items()
                if provider_name in self.providers
            }

            # Coletamos os resultados à medida que as threads terminam
            for future in concurrent.futures.as_completed(future_to_provider):
                provider_name = future_to_provider[future]
                try:
                    result = future.result() # Pega o resultado retornado pela função _fetch_provider_prices
                    if result:
                        all_priced_vms.extend(result)
                except Exception as exc:
                    logging.warning(f"CATALOG SERVICE: Exceção na thread de {provider_name.upper()}: {exc}")

        logging.info("CATALOG SERVICE: Todas as threads finalizaram. Consolidando resultados...")
        
        if not all_priced_vms:
            logging.info("CATALOG SERVICE: Nenhum preço foi retornado.")
            return []

        sorted_all_priced_vms = sorted(all_priced_vms, key=lambda vm: vm.price)
        if not group_by_price:
            return sorted_all_priced_vms
        else:
            grouped_vms = self.group_by_price(sorted_all_priced_vms)
            return grouped_vms

    def group_by_price(self, instances_sorted):
        MAX_REL_DIFF = 0.3
        groups = []
        current_group = []
        current_region = None
        current_provider = None

        for vm in instances_sorted:
            price = vm.price
            region = vm.region
            provider = vm.provider

            if not current_group:
                current_group.append(vm)
                current_region = region
                current_provider = provider
                min_price = price

            else:
                # se provider ou região diferente, fecha grupo e inicia novo
                if provider != current_provider or region != current_region:
                    groups.append(current_group)
                    current_group = [vm]
                    current_region = region
                    current_provider = provider
                    min_price = price
                else:
                    # mesma região, verifica diferença percentual entre menor e atual
                    if (price - min_price) / min_price <= MAX_REL_DIFF:
                        current_group.append(vm)
                    else:
                        # preço muito diferente, fecha grupo e inicia novo
                        groups.append(current_group)
                        current_group = [vm]
                        min_price = price

        # Adiciona último grupo
        if current_group:
            groups.append(current_group)  

        return groups   