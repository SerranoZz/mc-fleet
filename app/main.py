import argparse
import csv
import logging
import yaml
import sys  # Adicionado para usar sys.exit em caso de erro

from app.services.fleet_service import FleetService
from app.services.catalog_service import CatalogService
from app.provider_factory.factory import CloudProviderFactory
from app.clients.pricing_client import PricingClient

def main(args, catalog_config):
    providers_to_run = args.providers
    location = args.location
    num_vcpus = args.vcpus
    num_nodes = args.nodes
    allocation_strategy = args.strategy

    logging.info(
        f"\nIniciando provisionamento com os seguintes parâmetros:"
        f"\n  - Provedores: {', '.join(p.upper() for p in providers_to_run)}"
        f"\n  - Location: {location}"
        f"\n  - vCPUs por nó: {num_vcpus}"
        f"\n  - Número de nós: {num_nodes}"
        f"\n  - Estratégia: {allocation_strategy}"
    )

    available_providers = {
        name: CloudProviderFactory.get_provider(name)
        for name in providers_to_run
    }

    
    fleet_service = FleetService(available_providers)
    input("Aperte enter para deletar os fleets...")
    fleet_service.delete_fleet()

if __name__ == "__main__":
    logging.basicConfig(filename='./config/logs.log',
                        level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')
    
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("msrest").setLevel(logging.WARNING)        # para requests do SDK
    logging.getLogger("azure.core.pipeline").setLevel(logging.WARNING)
    logging.getLogger("azure.identity").setLevel(logging.WARNING)

    PROVIDERS = ['aws', 'azure']
    STRATEGIES = ['lowest-price', 'capacity-optimized', 'price-capacity-optimized']
    LOCATIONS = ['br', 'us', 'both']

    parser = argparse.ArgumentParser(description="Ferramenta de provisionamento de frota Multi-Cloud.")
    
    parser.add_argument(
        '--location',
        type=str,
        choices=LOCATIONS,
        default='both',
        help=f"Especifique uma região. Padrão: {LOCATIONS}"
    )

    parser.add_argument(
        '--providers',
        nargs='+',
        choices=PROVIDERS,
        default=PROVIDERS,
        help=f"Especifique um ou mais provedores. Padrão: {PROVIDERS}"
    )
    parser.add_argument(
        '--vcpus',
        type=int,
        choices=[2, 96],
        default=2,
        help="Número mínimo de vCPUs desejado para as instâncias da frota."
    )
    parser.add_argument(
        '--nodes',
        type=int,
        required=True,
        help="Quantidade de nós (VMs) a serem provisionados."
    )
    parser.add_argument(
        '--strategy',
        type=str,
        choices=STRATEGIES,
        default='lowest-price',
        help=f"Estratégia de alocação da frota. Padrão: 'lowest-price'. Opções: {STRATEGIES}"
    )
    
    args = parser.parse_args()

    try:
        with open('./config/vm_catalog.yaml', 'r') as f:
            catalog_config = yaml.safe_load(f)
    except FileNotFoundError:
        logging.error("Arquivo de configuração 'config/vm_catalog.yaml' não encontrado. Encerrando.")
        sys.exit(1)
    except yaml.YAMLError as e:
        logging.error(f"Erro ao processar o arquivo 'config/vm_catalog.yaml': {e}. Encerrando.")
        sys.exit(1)

    main(args, catalog_config)