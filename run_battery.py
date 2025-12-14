import argparse
import json
import logging
import yaml
import sys
import time
from datetime import datetime
import concurrent.futures
import test_runner 

def find_and_group_tests(all_enabled_tests):
    single_cloud_tests = [tc for tc in all_enabled_tests if tc.get('type') == 'single_cloud']
    multi_cloud_tests = [tc for tc in all_enabled_tests if tc.get('type') == 'multi_cloud']

    parallel_pairs = []
    unmatched_singles = []
    

    unmatched_pool = list(single_cloud_tests)

    while unmatched_pool:
        test_a = unmatched_pool.pop(0)
        partner_found = False
        
        for i, test_b in enumerate(unmatched_pool):
            if not test_a.get('providers') or not test_b.get('providers'):
                continue
            
            if (test_a['providers'][0] != test_b['providers'][0] and
                test_a.get('nodes') == test_b.get('nodes') and
                test_a.get('location') == test_b.get('location') and
                test_a.get('strategy') == test_b.get('strategy')):
                
                parallel_pairs.append([test_a, unmatched_pool.pop(i)])
                partner_found = True
                break  
        
        if not partner_found:
            unmatched_singles.append(test_a)

    return parallel_pairs, unmatched_singles, multi_cloud_tests

def main(config_path):
    try:
        with open(config_path, 'r') as f:
            test_config = yaml.safe_load(f)
    except FileNotFoundError:
        logging.error(f"Arquivo de configuração '{config_path}' não encontrado. Encerrando.")
        sys.exit(1)
    except yaml.YAMLError as e:
        logging.error(f"Erro ao processar o arquivo de configuração YAML: {e}. Encerrando.")
        sys.exit(1)

    all_results = []
    all_enabled_tests = [tc for tc in test_config.get('test_suite', []) if tc.get('enabled', False)]
    
    parallel_pairs, sequential_singles, sequential_multis = find_and_group_tests(all_enabled_tests)

    total_tests_to_run = (len(parallel_pairs) * 2) + len(sequential_singles) + len(sequential_multis)
    if total_tests_to_run == 0:
        logging.warning("Nenhum teste habilitado encontrado no arquivo de configuração.")
        return

    logging.info(f"Bateria de testes iniciada: {len(parallel_pairs)} par(es) em paralelo, {len(sequential_singles) + len(sequential_multis)} em sequência.")
    
    tests_processed_count = 0

    for pair in parallel_pairs:
        if tests_processed_count > 0:
            logging.info("Aguardando 3 minutos (180s) antes do próximo lote...")
            time.sleep(180)
        
        test_name_a = pair[0].get('name', 'Par Teste A')
        test_name_b = pair[1].get('name', 'Par Teste B')
        logging.info(f"--- INICIANDO LOTE PARALELO: '{test_name_a}' e '{test_name_b}' ---")

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_to_test_case = {executor.submit(test_runner.run_single_test, test_case): test_case for test_case in pair}
            for future in concurrent.futures.as_completed(future_to_test_case):
                test_case = future_to_test_case[future]
                test_name = test_case.get('name')
                try:
                    result = future.result()
                    all_results.append(result)
                    logging.info(f"--- [ {tests_processed_count+1}/{total_tests_to_run} ] TESTE PARALELO '{test_name}' CONCLUÍDO. Status: {result.get('status')} ---")
                except Exception as e:
                    logging.error(f"Erro crítico no teste paralelo '{test_name}': {e}", exc_info=True)
                    all_results.append({"test_name": test_name, "parameters": test_case, "status": "CRITICAL_FAILURE", "errors": [str(e)]})
                finally:
                    tests_processed_count += 1
        
        logging.info("--- LOTE PARALELO CONCLUÍDO ---")

    all_sequential_tests = sequential_singles + sequential_multis
    for test_case in all_sequential_tests:
        if tests_processed_count > 0:
            logging.info("Aguardando 3 minutos (180s) antes do próximo teste...")
            time.sleep(180)

        test_name = test_case.get('name')
        logging.info(f"--- [ {tests_processed_count+1}/{total_tests_to_run} ] EXECUTANDO TESTE SEQUENCIAL: '{test_name}' ---")
        try:
            result = test_runner.run_single_test(test_case)
            all_results.append(result)
            logging.info(f"--- TESTE SEQUENCIAL '{test_name}' CONCLUÍDO. Status: {result.get('status')} ---")
        except Exception as e:
            logging.error(f"Erro crítico no teste sequencial '{test_name}': {e}", exc_info=True)
            all_results.append({"test_name": test_name, "parameters": test_case, "status": "CRITICAL_FAILURE", "errors": [str(e)]})
        finally:
            tests_processed_count += 1

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f'./results/test_battery_results_{timestamp}.json'
    
    try:
        original_order_map = {case['name']: i for i, case in enumerate(test_config.get('test_suite', []))}
        all_results.sort(key=lambda r: original_order_map.get(r['test_name'], float('inf')))

        with open(output_filename, 'w', encoding='utf-8') as f:
            json.dump(all_results, f, indent=4, ensure_ascii=False)
        logging.info(f"Bateria de testes finalizada. Resultados salvos em '{output_filename}'.")
    except Exception as e:
        logging.error(f"Não foi possível salvar o arquivo de resultados: {e}")

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler('./config/battery_logs.log'),
        ]
    )
    
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("msrest").setLevel(logging.WARNING)
    logging.getLogger("azure.core.pipeline").setLevel(logging.WARNING)
    logging.getLogger("azure.identity").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    parser = argparse.ArgumentParser(description="Orquestrador de bateria de testes de provisionamento Multi-Cloud.")
    parser.add_argument(
        '--config', type=str, default='./config/test_battery_config.yaml',
        help="Caminho para o arquivo de configuração da bateria de testes."
    )
    args = parser.parse_args()

    main(args.config)

