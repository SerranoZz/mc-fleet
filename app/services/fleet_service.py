import logging

class FleetService:
    def __init__(self, providers):
        self.providers = providers
        self.fleets = {}


    def provision_fleet_multi_cloud(self, sorted_groups, target_capacity, allocation_strategy):

        provisioned_fleets_this_run = {}
        capacity_fulfilled = 0
        groups_to_try = list(sorted_groups) 

        logging.info(f"Iniciando provisionamento. Meta: {target_capacity} instâncias.")

        while capacity_fulfilled < target_capacity and groups_to_try:
            capacity_needed_now = target_capacity - capacity_fulfilled
            current_group = groups_to_try.pop(0)

            provider_name = current_group[0].provider
            provider = self.providers.get(provider_name)

            if not provider:
                logging.warning(f"Provedor '{provider_name}' não encontrado. Pulando.")
                continue

            fleet_id, new_instances, errors = provider.create_fleet(
                current_group,
                allocation_strategy,
                capacity_needed_now
            )

            if fleet_id and new_instances:
                num_created = len(new_instances)
                
                provisioned_fleets_this_run[fleet_id] = new_instances
                
                capacity_fulfilled += num_created

                logging.info(f"Sucesso! Frota '{fleet_id}' criada na {provider_name.upper()} com {num_created} instâncias.")
                logging.info(f"Capacidade total atingida: {capacity_fulfilled}/{target_capacity}")
            else:
                logging.warning(f"Falha ao provisionar instâncias com o provedor {provider_name.upper()}. Tentando próxima opção.")
        

        if provisioned_fleets_this_run:
            self.fleets.update(provisioned_fleets_this_run)
            logging.info("Processo de provisionamento finalizado.")
        else:
            logging.error("Não foi possível provisionar nenhuma instância para atender à capacidade desejada.")

        return provisioned_fleets_this_run
    

    def provision_fleet_single_cloud(self, instances, target_capacity, allocation_strategy):

        provisioned_fleets_this_run = {}
        capacity_fulfilled = 0

        logging.info(f"Iniciando provisionamento. Meta: {target_capacity} instâncias.")

        provider_name = instances[0].provider
        provider = self.providers.get(provider_name)

        fleet_id, new_instances, errors = provider.create_fleet(
            instances,
            allocation_strategy,
            target_capacity
        )

        if fleet_id and new_instances:
            num_created = len(new_instances)
            
            provisioned_fleets_this_run[fleet_id] = new_instances
            
            capacity_fulfilled += num_created

            logging.info(f"Sucesso! Frota '{fleet_id}' criada na {provider_name.upper()} com {num_created} instâncias.")
            logging.info(f"Capacidade total atingida: {capacity_fulfilled}/{target_capacity}")
        else:
            logging.warning(f"Falha ao provisionar instâncias com o provedor {provider_name.upper()}. Tentando próxima opção.")
        

        if provisioned_fleets_this_run:
            self.fleets.update(provisioned_fleets_this_run)
            logging.info("Processo de provisionamento finalizado.")
        else:
            logging.error("Não foi possível provisionar nenhuma instância para atender à capacidade desejada.")

        return provisioned_fleets_this_run
    


    

    def delete_fleet(self):
        for provider_name in self.providers:
            provider = self.providers.get(provider_name)
            provider.delete_fleet()
