import glob
import json
import pandas as pd
import os

# Lista de arquivos de resultados (cada um é uma rodada de testes)
arquivos = glob.glob("./results/*.json")

rows = []

for run_id, arq in enumerate(arquivos, start=1):
    with open(arq, "r") as f:
        data = json.load(f)

    for test in data:
        test_name = test["test_name"]
        provisioning_time = test["provisioning_time_seconds"]

        # calcular preço médio ponderado e TOTAL DE INSTÂNCIAS do teste inteiro
        total_vms_test = 0
        total_price_test = 0
        for fleet in test["fleets"]:
            for s in fleet["summary"]:
                total_vms_test += s["count"]
                total_price_test += s["count"] * s["price_per_instance"]

        avg_price_test = total_price_test / total_vms_test if total_vms_test > 0 else 0

        for fleet in test["fleets"]:
            fleet_name = fleet["fleet_id"]
            total_quantity = 0
            for s in fleet["summary"]:
                instance_type = s["instance_type"]
                region_az = s["region_az"]
                quantity = s["count"]
                price = s["price_per_instance"]
                total_price = quantity * price
                total_quantity += quantity

                rows.append({
                    "run_id": run_id,
                    "test_name": test_name,
                    "fleet_name": fleet_name,
                    "provisioning_time": provisioning_time,
                    "instance_type": instance_type,
                    "region_az": region_az,
                    "quantity": quantity,
                    "price": price,
                    "total_price": total_price,
                    "avg_price_test": avg_price_test,
                    # --- MODIFICAÇÃO 1: Adiciona o total de instâncias alocadas no teste ---
                    "allocated_instances": total_vms_test
                })

# Criar DataFrame
df = pd.DataFrame(rows)

n_values = [10, 100, 200, 250]

for test_name, group in df.groupby("test_name"):
    safe_name = test_name.replace(" ", "_").replace("/", "-")

    # calcular média das execuções
    avg_row = {
        "run_id": "mean",
        "test_name": test_name,
        "fleet_name": "",
        "provisioning_time": group["provisioning_time"].mean(),
        "instance_type": "",
        "region_az": "",
        "quantity": "",
        "price": "",
        "total_price": "",
        "avg_price_test": group["avg_price_test"].mean(),
        # --- MODIFICAÇÃO 2: Adiciona a MÉDIA do total de instâncias alocadas ---
        "allocated_instances": int(group["allocated_instances"].mean())
    }

    # adicionar linha de média
    group_with_mean = pd.concat([group, pd.DataFrame([avg_row])], ignore_index=True)

    n_value = 0
    if 'N100' in safe_name:
        n_value = 100
    elif 'N10' in safe_name:
        n_value = 10
    elif 'N200' in safe_name:
        n_value = 200
    elif 'N250' in safe_name:
        n_value = 250
    elif 'N400' in safe_name:
        n_value = 400
    elif 'N600' in safe_name:
        n_value = 600
    
    # Garante que o diretório de destino exista
    output_dir = f"./csv_results/selection_results/N{n_value}/"
    os.makedirs(output_dir, exist_ok=True)
    group_with_mean.to_csv(f"{output_dir}{safe_name}.csv", index=False)


print("CSVs gerados com linhas de média e total de instâncias alocadas incluídos!")