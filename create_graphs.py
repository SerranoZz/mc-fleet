import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import glob
import os
from adjustText import adjust_text # <--- MUDANÇA: Importar a nova biblioteca
# ==============================================================================
# LOGIC AND DATA PROCESSING FUNCTIONS
# ==============================================================================
def get_instance_distribution(df):
    """
    Calcula a média de instâncias alocadas por provedor (AWS/Azure) em todas as rodadas (runs),
    usando a coluna 'quantity' para a contagem correta.
    Retorna um dicionário com a contagem média arredondada. Ex: {'AWS': 150, 'Azure': 250}
    """
    # 1. Filtra apenas as rodadas de execução, ignorando a linha de média
    df_runs = df[df['run_id'] != 'mean'].copy()
    
    # 2. Encontra os identificadores únicos de cada rodada
    run_ids = df_runs['run_id'].unique()
    
    # 3. Armazena a contagem de instâncias por provedor para cada rodada
    distributions_per_run = []
    for run_id in run_ids:
        df_da_rodada = df_runs[df_runs['run_id'] == run_id]
        
        # --- MUDANÇA CRÍTICA AQUI ---
        # Usa a coluna 'quantity' em vez de 'allocated_instances'
        aws_instances = df_da_rodada[df_da_rodada['fleet_name'].str.contains('aws', case=False)]['quantity'].sum()
        azure_instances = df_da_rodada[df_da_rodada['fleet_name'].str.contains('azure', case=False)]['quantity'].sum()
        
        distributions_per_run.append({'AWS': aws_instances, 'Azure': azure_instances})

    # 4. Calcula a média das contagens de todas as rodadas
    if not distributions_per_run:
        return {'AWS': 0, 'Azure': 0}

    avg_aws = sum(d['AWS'] for d in distributions_per_run) / len(distributions_per_run)
    avg_azure = sum(d['Azure'] for d in distributions_per_run) / len(distributions_per_run)

    distribution = {
        'AWS': int(round(avg_aws)),
        'Azure': int(round(avg_azure))
    }

    # 5. Ajuste final para garantir que a soma bate com o total da linha 'mean'
    total_mean_instances = int(df[df['run_id'] == 'mean']['allocated_instances'].iloc[0])
    current_total = distribution['AWS'] + distribution['Azure']
    
    if current_total != total_mean_instances and current_total > 0:
        diff = total_mean_instances - current_total
        if distribution['AWS'] > distribution['Azure']:
            distribution['AWS'] += diff
        else:
            distribution['Azure'] += diff
            
    return distribution


def get_allocation_distribution_with_regions(df):

    df_runs = df[df['run_id'] != 'mean'].copy()
    
    providers = {
        'AWS': set(),
        'Azure': set()
    }

    for index, row in df_runs.iterrows():
        fleet_name = str(row.get('fleet_name', '')).lower()
        region_az = str(row.get('region_az', ''))

        if not region_az:
            continue

        if 'aws' in fleet_name:
            region = region_az[:-1] if region_az[-1].isalpha() else region_az
            providers['AWS'].add(region)
        
        if 'azure' in fleet_name:
            providers['Azure'].add(region_az)

    output_parts = []
    if providers['AWS']:
        aws_regions = ", ".join(sorted(list(providers['AWS'])))
        output_parts.append(f"AWS ({aws_regions})")
    if providers['Azure']:
        azure_regions = ", ".join(sorted(list(providers['Azure'])))
        output_parts.append(f"Azure ({azure_regions})")

    return "/".join(output_parts)


# ==============================================================================
# CHART GENERATION FUNCTIONS
# ==============================================================================

def gerar_grafico_preco_n10(output_dir):
    """Generates the PRICE bar chart for N=10 with 3 strategies."""
    print("Generating Price chart for N=10...")
    
    arquivos = glob.glob("./csv_results/selection_results/N10/*.csv")
    if not arquivos:
        print("  WARNING: No files found for N=10.")
        return

    resultados = {
        "MC-Fleet": None, "AWS sa-east-1": {},
        "AWS us-east-1": {}, "Azure brazilsouth": {}
    }

    for arq in arquivos:
        df = pd.read_csv(arq)
        mean_row = df[df["run_id"] == "mean"].iloc[0]
        test_name = mean_row["test_name"].lower()
        avg_price = mean_row["avg_price_test"]

        if "multi-cloud" in test_name:
            resultados["MC-Fleet"] = avg_price
        elif "sa-east-1" in test_name:
            if "price-capacity-optimized" in test_name: resultados["AWS sa-east-1"]["price-capacity-optimized"] = avg_price
            elif "capacity-optimized" in test_name: resultados["AWS sa-east-1"]["capacity-optimized"] = avg_price
            elif "lowest-price" in test_name: resultados["AWS sa-east-1"]["lowest-price"] = avg_price
        elif "us-east-1" in test_name:
            if "price-capacity-optimized" in test_name: resultados["AWS us-east-1"]["price-capacity-optimized"] = avg_price
            elif "capacity-optimized" in test_name: resultados["AWS us-east-1"]["capacity-optimized"] = avg_price
            elif "lowest-price" in test_name: resultados["AWS us-east-1"]["lowest-price"] = avg_price
        elif "brazilsouth" in test_name:
            if "price-capacity-optimized" in test_name: resultados["Azure brazilsouth"]["price-capacity-optimized"] = avg_price
            elif "capacity-optimized" in test_name: resultados["Azure brazilsouth"]["capacity-optimized"] = avg_price
            elif "lowest-price" in test_name: resultados["Azure brazilsouth"]["lowest-price"] = avg_price

    cenarios = ['MC-Fleet', 'AWS sa-east-1', 'AWS us-east-1', "Azure brazilsouth"]
    estrategias = ['MC-Fleet lowest-price', 'lowest-price', 'capacity-optimized', 'price-capacity-optimized']
    
    dados_precos = [
        [resultados.get("MC-Fleet", 0) * 10],
        [resultados["AWS sa-east-1"].get("lowest-price", 0) * 10, resultados["AWS sa-east-1"].get("capacity-optimized", 0) * 10, resultados["AWS sa-east-1"].get("price-capacity-optimized", 0) * 10],
        [resultados["AWS us-east-1"].get("lowest-price", 0) * 10, resultados["AWS us-east-1"].get("capacity-optimized", 0) * 10, resultados["AWS us-east-1"].get("price-capacity-optimized", 0) * 10],
        [resultados["Azure brazilsouth"].get("lowest-price", 0) * 10, resultados["Azure brazilsouth"].get("capacity-optimized", 0) * 10, resultados["Azure brazilsouth"].get("price-capacity-optimized", 0) * 10]
    ]
    
    cores = ['#00A88F', '#6A51A3', '#49006A', '#238B8F']
    largura = 0.27
    x = np.arange(len(cenarios))
    offsets = [-largura, 0, largura]

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.yaxis.grid(True, linestyle='--', alpha=0.6)
    ax.set_axisbelow(True)

    ax.bar(x[0], dados_precos[0][0], width=largura, color=cores[0], label=estrategias[0])
    ax.text(x[0], dados_precos[0][0] + 0.05, f'{dados_precos[0][0]:.2f}', ha='center', fontsize=9)

    for i in range(1, len(cenarios)):
        for j in range(3):
            valor = dados_precos[i][j]
            pos_x = x[i] + offsets[j]
            ax.bar(pos_x, valor, width=largura, color=cores[j + 1], label=estrategias[j + 1] if i == 1 else "")
            ax.text(pos_x, valor + 0.02, f'{valor:.2f}', ha='center', fontsize=9)
    
    ax.set_title('Average Price Comparison per Selection (N=10)', fontsize=14)
    ax.set_ylabel('Average Price per Selection (USD)', fontsize=11)
    ax.set_xlabel('Execution Scenario', fontsize=11)
    ax.set_xticks(x)
    ax.set_xticklabels(cenarios, fontsize=10)
    ax.legend(title='Allocation Strategy', fontsize=9)
    
    plt.tight_layout()
    output_filename = os.path.join(output_dir, 'avg_price_comparison_N10.png')
    plt.savefig(output_filename, dpi=400)
    plt.close(fig)
    print(f"  > Chart saved to: '{output_filename}'")


def gerar_graficos_preco_n_maior(n_values, output_dir):
    """Generates PRICE bar charts for N > 10 with stacked MC-Fleet bar."""
    print("Generating Price charts for N > 10...")

    # ... (a lógica de leitura e processamento de dados permanece a mesma) ...
    for n in n_values:
        # ... (código de leitura de arquivos e processamento de dados) ...
        # (código omitido para brevidade, mantenha o seu)
        arquivos = glob.glob(f"./csv_results/selection_results/N{n}/*.csv")
        if not arquivos:
            print(f"   WARNING: No files found for N={n}. Skipping.")
            continue
        
        resultados = {
            "MC-Fleet": {"price": None, "distribution": None},
            "AWS sa-east-1": {},
            "AWS us-east-1": {},
            "Azure brazilsouth": {}
        }

        cenarios_com_dados = set()
        for arq in arquivos:
            df = pd.read_csv(arq)
            mean_row = df[df["run_id"] == "mean"].iloc[0]
            test_name = mean_row["test_name"].lower()
            avg_price = mean_row["avg_price_test"]
            allocated_instances = int(mean_row["allocated_instances"])
            
            if "multi-cloud" in test_name:
                resultados["MC-Fleet"]["price"] = avg_price
                resultados["MC-Fleet"]["distribution"] = get_instance_distribution(df)
                cenarios_com_dados.add("MC-Fleet")
            elif "lowest-price" in test_name:
                if "sa-east-1" in test_name:
                    resultados["AWS sa-east-1"]["price"] = avg_price
                    resultados["AWS sa-east-1"]["instances"] = allocated_instances
                    cenarios_com_dados.add("AWS sa-east-1")
                elif "us-east-1" in test_name:
                    resultados["AWS us-east-1"]["price"] = avg_price
                    resultados["AWS us-east-1"]["instances"] = allocated_instances
                    cenarios_com_dados.add("AWS us-east-1")
                elif "brazilsouth" in test_name:
                    resultados["Azure brazilsouth"]["price"] = avg_price
                    resultados["Azure brazilsouth"]["instances"] = allocated_instances
                    cenarios_com_dados.add("Azure brazilsouth")

        cenarios = ['MC-Fleet', 'AWS sa-east-1', 'AWS us-east-1', 'Azure brazilsouth']
        cenarios_finais = [c for c in cenarios if c in cenarios_com_dados]

        mc_fleet_price = resultados["MC-Fleet"].get("price", 0)
        dist = resultados["MC-Fleet"].get("distribution", {'AWS': 0, 'Azure': 0})
        
        total_allocated_mc = dist.get('AWS', 0) + dist.get('Azure', 0)
        if total_allocated_mc > 0:
            custo_aws_total = mc_fleet_price * dist['AWS']
            custo_azure_total = mc_fleet_price * dist['Azure']
        else:
            custo_aws_total = 0
            custo_azure_total = 0
        
        dados_precos = {
            "MC-Fleet_AWS_total": custo_aws_total,
            "MC-Fleet_Azure_total": custo_azure_total,
        }
        for cenario in cenarios_finais:
            if cenario != "MC-Fleet":
                price = resultados[cenario].get("price", 0)
                instances = resultados[cenario].get("instances", 0)
                dados_precos[cenario] = price * instances


        fig, ax = plt.subplots(figsize=(7, 5))
        ax.yaxis.grid(True, linestyle='--', alpha=0.3)
        ax.set_axisbelow(True)

        # --- MUDANÇA: APLICANDO A NOVA PALETA DE CORES ---
        cores_mc_aws = '#00A88F'     # Teal para MC-Fleet (AWS)
        cores_mc_azure = "#067967"   # Teal Escuro para MC-Fleet (Azure)
        cor_single_cloud = '#6A51A3' # Roxo para lowest-price

        handles, labels = [], []

        for cenario in cenarios_finais:
            if cenario == "MC-Fleet":
                bar1 = ax.bar(cenario, dados_precos["MC-Fleet_AWS_total"], width=0.5, 
                              color=cores_mc_aws, label=f'MC-Fleet (AWS: {dist["AWS"]} VMs)')
                bar2 = ax.bar(cenario, dados_precos["MC-Fleet_Azure_total"], width=0.5, 
                              bottom=dados_precos["MC-Fleet_AWS_total"], color=cores_mc_azure, 
                              label=f'MC-Fleet (Azure: {dist["Azure"]} VMs)')
                
                total_mc_fleet = dados_precos["MC-Fleet_AWS_total"] + dados_precos["MC-Fleet_Azure_total"]
                ax.text(cenario, total_mc_fleet, f'{total_mc_fleet:.2f}', ha='center', va='bottom', fontsize=9)
                handles.extend([bar1, bar2])
            else:
                label_single_cloud = 'Single-Cloud lowest-price' if 'Single-Cloud lowest-price' not in [h.get_label() for h in handles] else ""
                
                bar = ax.bar(cenario, dados_precos[cenario], width=0.5, 
                              color=cor_single_cloud, label=label_single_cloud)
                ax.text(cenario, dados_precos[cenario], f'{dados_precos[cenario]:.2f}', ha='center', va='bottom', fontsize=9)
                if label_single_cloud:
                    handles.append(bar)

        labels = [h.get_label() for h in handles]
        ax.legend(handles, labels, title='Allocation Strategy', fontsize=8, title_fontsize=9, loc='best')

        ax.set_title(f'Price Comparison (N={n})', fontsize=12)
        ax.set_ylabel('Total Price (USD)', fontsize=10)
        ax.set_xlabel('Execution Scenario', fontsize=10)
        ax.tick_params(axis='both', which='major', labelsize=9, rotation=0)
        
        bottom, top = ax.get_ylim()
        ax.set_ylim(bottom, top * 1.15) 
        
        plt.tight_layout(pad=0.5)
        output_filename = os.path.join(output_dir, f'avg_price_comparison_N{n}.png')
        plt.savefig(output_filename, dpi=400)
        plt.close(fig)
        print(f"   > Chart for N={n} saved to: '{output_filename}'")


# <--- CORREÇÃO AQUI
def get_simplified_distribution(dist_string):
    """
    Simplifica a string de distribuição para ser mais legível.
    Recebe: "AWS (sa-east-1, us-east-1)/Azure (brazilsouth)"
    Retorna: "AWS(sa-1,us-1)/Az(br-south)"
    """
    if not dist_string or not isinstance(dist_string, str):
        return ""

    # Dicionários para abreviação
    provider_map = {"Azure": "Az", "AWS": "AWS"}
    region_map = {
        "sa-east-1": "sa-1",
        "us-east-1": "us-1",
        "brazilsouth": "br-south"
    }

    parts = dist_string.split('/')
    simplified_parts = []

    for part in parts:
        try:
            provider, regions_raw = part.split(' (')
            regions_raw = regions_raw.strip(')')
            
            s_provider = provider_map.get(provider.strip(), provider.strip())
            
            regions = [r.strip() for r in regions_raw.split(',')]
            s_regions = [region_map.get(r, r) for r in regions]
            
            simplified_parts.append(f"{s_provider}({','.join(s_regions)})")
        except ValueError:
            # Caso a string não esteja no formato esperado, retorna a original da parte
            simplified_parts.append(part)
            
    return "/".join(simplified_parts)

def gerar_grafico_tempo_vs_n_enxuto(n_values, output_dir):
    """Gera o gráfico TEMPO vs. N para caber em uma coluna de artigo."""
    print("Generating compact Provisioning Time vs. N chart for article column...")
    scenarios = ['MC-Fleet', 'AWS sa-east-1', 'AWS us-east-1', 'Azure brazilsouth']
    plot_data = {s: [] for s in scenarios}

    for n in n_values:
        data_found_for_n = {s: None for s in scenarios}
        arquivos = glob.glob(f"./csv_results/selection_results/N{n}/*.csv")
        if arquivos:
            for arq in arquivos:
                df = pd.read_csv(arq)
                mean_row = df[df["run_id"] == "mean"].iloc[0]
                test_name = df.iloc[0]['test_name'].lower()
                tempo, instancias = mean_row['provisioning_time'], int(mean_row['allocated_instances'])
                dist = ''
                if "multi-cloud" in test_name:
                    dist_original = get_allocation_distribution_with_regions(df)
                    dist = get_simplified_distribution(dist_original)
                    data_found_for_n['MC-Fleet'] = (tempo, instancias, dist)
                elif "lowest-price" in test_name:
                    if "sa-east-1" in test_name: data_found_for_n['AWS sa-east-1'] = (tempo, instancias, dist)
                    elif "us-east-1" in test_name: data_found_for_n['AWS us-east-1'] = (tempo, instancias, dist)
                    elif "brazilsouth" in test_name: data_found_for_n['Azure brazilsouth'] = (tempo, instancias, dist)
        
        for scenario in scenarios:
            plot_data[scenario].append(data_found_for_n[scenario] if data_found_for_n[scenario] else (np.nan, np.nan, ''))

    fig, ax = plt.subplots(figsize=(7, 5))
    cores = {
        'MC-Fleet': '#1f77b4', 'AWS sa-east-1': '#ff7f0e',
        'AWS us-east-1': '#2ca02c', 'Azure brazilsouth': '#d62728'
    }
    marcadores = {'MC-Fleet': 'o', 'AWS sa-east-1': 's', 'AWS us-east-1': '^', 'Azure brazilsouth': 'D'}
    texts = []

    # Desenha as linhas primeiro para definir os limites do eixo Y
    for cenario, data_points in plot_data.items():
        tempos, _, _ = zip(*data_points)
        valid_indices = [i for i, t in enumerate(tempos) if not np.isnan(t)]
        n_valid = [n_values[i] for i in valid_indices]
        tempos_valid = [tempos[i] for i in valid_indices]
        if not tempos_valid: continue
        ax.plot(n_valid, tempos_valid, marker=marcadores.get(cenario), linestyle='-', label=cenario, color=cores.get(cenario, 'black'), markersize=5)
    
    # Define os limites e a legenda
    ax.set_ylim(bottom=0)
    ax.legend(title='Execution Scenario', fontsize=7, title_fontsize=8, loc='best')

    # <--- MUDANÇA: Calcula o offset vertical para os rótulos
    offset = (ax.get_ylim()[1] - ax.get_ylim()[0]) * 0.015

    # Adiciona os textos com o novo offset e tamanho de fonte
    for cenario, data_points in plot_data.items():
        tempos, instancias, dists = zip(*data_points)
        valid_indices = [i for i, t in enumerate(tempos) if not np.isnan(t)]
        for i in valid_indices:
            label = f"{int(instancias[i])}"
            if cenario == 'MC-Fleet' and dists[i] and '/' in dists[i]:
                label += f"\n({dists[i]})"
            
            # <--- MUDANÇA: fontsize aumentado e offset adicionado
            texts.append(ax.text(n_values[i], tempos[i] + offset, label, ha='center', va='bottom', fontsize=8, fontweight='normal'))

    adjust_text(texts, 
                force_points=(0.2, 0.2), force_text=(0.5, 0.5),
                expand_points=(1.1, 1.1), expand_text=(1.2, 1.2),
                arrowprops=dict(arrowstyle='-', color='gray', lw=0.3, alpha=0.7))

    ax.set_title('Average Provisioning Time vs. Number of Instances (N)', fontsize=10)
    ax.set_xlabel('Number of Requested Instances (N)', fontsize=9)
    ax.set_ylabel('Average Provisioning Time (s)', fontsize=9)
    ax.set_xticks(n_values)
    ax.tick_params(axis='both', which='major', labelsize=9)
    ax.grid(True, which='both', linestyle='--', alpha=0.6, linewidth=0.5)
    
    output_filename = os.path.join(output_dir, 'provisioning_time_comparison_compact.png')
    plt.tight_layout(pad=0.5)
    plt.savefig(output_filename, dpi=400)
    plt.close(fig)
    print(f"  > Compact chart saved to: '{output_filename}'")


def gerar_grafico_tempo_vs_n_melhorado(n_values, output_dir):
    """Gera o gráfico TEMPO vs. N com rótulos ajustados e melhor visualização."""
    print("Generating improved Provisioning Time vs. N chart...")

    scenarios = ['MC-Fleet', 'AWS sa-east-1', 'AWS us-east-1', 'Azure brazilsouth']
    plot_data = {s: [] for s in scenarios}

    # <--- MUDANÇA: Lógica de dados ajustada para lidar com valores ausentes
    for n in n_values:
        data_found_for_n = {s: None for s in scenarios}
        arquivos = glob.glob(f"./csv_results/selection_results/N{n}/*.csv")

        if arquivos:
            # Processa os arquivos como antes
            # Esta parte do código de extração pode ser mantida como a sua original
            # O exemplo abaixo simula a extração para os cenários existentes
            for arq in arquivos:
                df = pd.read_csv(arq)
                mean_row = df[df["run_id"] == "mean"].iloc[0]
                test_name = df.iloc[0]['test_name'].lower()
                tempo = mean_row['provisioning_time']
                instancias = int(mean_row['allocated_instances'])
                
                dist = ''
                if "multi-cloud" in test_name:
                    dist = get_simplified_distribution(get_allocation_distribution_with_regions(df)) # <--- MUDANÇA: Simplifica o rótulo
                    data_found_for_n['MC-Fleet'] = (tempo, instancias, dist)
                elif "lowest-price" in test_name:
                    if "sa-east-1" in test_name: data_found_for_n['AWS sa-east-1'] = (tempo, instancias, dist)
                    elif "us-east-1" in test_name: data_found_for_n['AWS us-east-1'] = (tempo, instancias, dist)
                    elif "brazilsouth" in test_name: data_found_for_n['Azure brazilsouth'] = (tempo, instancias, dist)

        # Adiciona os dados encontrados ou NaN se nenhum dado foi encontrado para um cenário
        for scenario in scenarios:
            if data_found_for_n[scenario]:
                plot_data[scenario].append(data_found_for_n[scenario])
            else:
                plot_data[scenario].append((np.nan, np.nan, ''))

    fig, ax = plt.subplots(figsize=(14, 8)) # <--- MUDANÇA: Gráfico um pouco maior
    
    # <--- MUDANÇA: Dicionários de cores e marcadores
    cores = {'MC-Fleet': '#1f77b4', 'AWS sa-east-1': '#ff7f0e', 'AWS us-east-1': "#11db11", 'Azure brazilsouth': '#d62728'}
    marcadores = {'MC-Fleet': 'o', 'AWS sa-east-1': 's', 'AWS us-east-1': '^', 'Azure brazilsouth': 'D'}
    
    texts = [] # <--- MUDANÇA: Lista para armazenar os objetos de texto

    for cenario, data_points in plot_data.items():
        tempos, instancias, dists = zip(*data_points)
        
        # Filtra valores NaN para que a linha seja desenhada corretamente com interrupções
        valid_indices = [i for i, t in enumerate(tempos) if not np.isnan(t)]
        n_valid = [n_values[i] for i in valid_indices]
        tempos_valid = [tempos[i] for i in valid_indices]

        if not tempos_valid: continue

        ax.plot(n_valid, tempos_valid, marker=marcadores.get(cenario), linestyle='-', label=cenario, color=cores.get(cenario, 'black'))
        
        for i in valid_indices:
            label = f"{int(instancias[i])}"
            if cenario == 'MC-Fleet' and dists[i] and '/' in dists[i]: # <--- MUDANÇA AQUI
                label += f"\n({dists[i]})"
            
            # <--- MUDANÇA: Adiciona o texto à lista em vez de plotá-lo diretamente
            texts.append(ax.text(n_values[i], tempos[i], label, ha='center', va='bottom', fontsize=9, fontweight='bold'))

    # <--- MUDANÇA: Chamada única para ajustar todos os textos
    adjust_text(texts, arrowprops=dict(arrowstyle='->', color='gray', lw=0.5))

    ax.set_title('Average Provisioning Time vs. Number of Instances (N)', fontsize=16)
    ax.set_xlabel('Number of Requested Instances (N)', fontsize=12)
    ax.set_ylabel('Average Provisioning Time (s)', fontsize=12)
    ax.set_xticks(n_values)
    ax.set_ylim(bottom=0)
    current_ylim = ax.get_ylim()
    ax.set_ylim(current_ylim[0], current_ylim[1] * 1.1)
    ax.legend(title='Execution Scenario', fontsize=10)
    ax.grid(True, which='both', linestyle='--', alpha=0.6) # <--- MUDANÇA: Grid para ambos os eixos

    output_filename = os.path.join(output_dir, 'provisioning_time_comparison_final.png')
    plt.tight_layout()
    plt.savefig(output_filename, dpi=400)
    plt.close(fig)
    print(f"  > Chart saved to: '{output_filename}'")


# ==============================================================================
# MAIN EXECUTION BLOCK
# ==============================================================================
if __name__ == "__main__":
    OUTPUT_DIR = './graphs/'
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Generate the price charts
    gerar_grafico_preco_n10(OUTPUT_DIR)
    gerar_graficos_preco_n_maior([100, 200, 250, 400], OUTPUT_DIR)
    
    # Generate the time vs. N chart
    gerar_grafico_tempo_vs_n_enxuto([10, 100, 200, 250, 400], OUTPUT_DIR)
    
    print("\nAll charts were generated successfully!")