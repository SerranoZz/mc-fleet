import logging
import requests # type: ignore
import concurrent.futures
from ..core.models import VMSpec


class PricingClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.trust_env = False
        logging.info("PricingClient inicializado com sessão configurada.")

    def get_prices_for(self, all_data):
        logging.info(f"PricingClient: Recebi {len(all_data)} itens para cotar em paralelo.")
        vms_with_prices = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_item = {executor.submit(self._fetch_single_price, item): item for item in all_data}
            for future in concurrent.futures.as_completed(future_to_item):
                item = future_to_item[future]
                try:
                    price, az = future.result()
                    
                    if price is not None:
                        vms_with_prices.append(
                            VMSpec(
                                provider=item["provider"],
                                instance_type=item["instance_type"],
                                region=item["region"],
                                price=price,
                                region_az=az
                            )
                        )
                except Exception as exc:
                    logging.error(f"Exceção gerada para o item {item['instance_type']}: {exc}")

        logging.info(f"Cotação finalizada. {len(vms_with_prices)} VMs com preços válidos.")\
        
        return vms_with_prices

    def _fetch_single_price(self, item):
        provider = item["provider"]
        instance_type = item["instance_type"]
        region = item["region"]
        
        params = {'type': instance_type, 'region': region, 'market': 'spot', 'provider': provider}
        
        try:
            response = self.session.get("url", params=params, timeout=15) 
            response.raise_for_status() 
            
            data = response.json()
            if not data.get('prices_spot'):
                logging.warning(f"Resposta de preço vazia para {provider}/{instance_type}.")
                return None, None

            az_min = min(data['prices_spot'], key=data['prices_spot'].get)
            price_min = data['prices_spot'][az_min]
            return float(price_min), az_min
            
        except requests.exceptions.HTTPError as e:
            logging.warning(f"Falha ao buscar preço para {provider}/{instance_type}. Status: {e.response.status_code}")
            return None, None
        except requests.exceptions.RequestException as e:
            logging.error(f"Erro de conexão ao buscar preço para {provider}/{instance_type}: {e}")
            return None, None