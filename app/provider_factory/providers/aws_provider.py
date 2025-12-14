import logging
import re
import subprocess

import yaml
from ..abstract_factory import AbstractCloudProvider
import boto3 # type: ignore
from ...core.models import FleetVmSpec

class AWSProvider(AbstractCloudProvider):
    FLEET_NAME = f'AWS-FLEET'
    FLEET_NUM = 1

    def get_all_vms(self, provider_config, vcpus, location):
        LOCATION_MAP = {
            'br': ['sa-east-1'],
            'us': ['us-east-1']
        }

        all_provider_regions = provider_config.get('regions', {})

        target_region_names = LOCATION_MAP.get(location)

        if target_region_names:
            regions_to_process = {
                name: data 
                for name, data in all_provider_regions.items() 
                if name in target_region_names
            }
        else:
            regions_to_process = all_provider_regions

        vms = [
            {
                'provider': 'aws',
                'instance_type': instance_type["name"],
                'vcpus': instance_type['vcpus'],
                'region': region_name,
                'market': 'spot'
            }
            for region_name, region_data in regions_to_process.items()
            for instance_type in region_data.get('instance_types', [])
            if instance_type.get("vcpus", 0) == vcpus
        ]   

        return vms
    

    def create_fleet(self, instances, allocation_strategy, target_capacity, tag='MultiCloud - FVBR'):
        
        region = instances[0].region
        session = boto3.Session(region_name=region)
        ec2_client = session.client("ec2")

        overrides = self._instance_template_config(instances)

        launch_template_config = [
            {
                "LaunchTemplateSpecification": {
                    "LaunchTemplateName": "Template",
                    "Version": "$Default"
                },
                "Overrides": overrides  
            }
        ]
    
        fleet_config = {
            "LaunchTemplateConfigs": launch_template_config,
            "TargetCapacitySpecification": {
                "TotalTargetCapacity": target_capacity,
                "DefaultTargetCapacityType": "spot"
            },
            "SpotOptions": {
                "AllocationStrategy": allocation_strategy
                #"MaxTotalPrice": str(spot_price) if spot_price else None
            },
            "Type": "instant",
            "TagSpecifications" : [{
                    'ResourceType': 'instance',
                    'Tags':[{'Key': 'Name', 'Value': tag}]
            }]
        }
    
        try:
            fleet_name = f'{self.FLEET_NAME}-{self.FLEET_NUM}'
            logging.info(f"Tentando criar Frota com {target_capacity} instâncias na região {region}...")
            response = ec2_client.create_fleet(**fleet_config)
            fleet_id = response.get("FleetId")
            instance_ids = [inst for fleet in response.get("Instances", []) for inst in fleet["InstanceIds"]]
            errors = response.get('Errors', [])

            if not instance_ids:
                return fleet_id, [], errors

            logging.info(f"Frota {fleet_id} criada com {len(instance_ids)} instâncias. Aguardando execução...")

            waiter = ec2_client.get_waiter('instance_running')
            waiter.wait(InstanceIds=instance_ids, WaiterConfig={'Delay': 15, 'MaxAttempts': 40})
            
            logging.info(f"Instâncias em execução. Buscando todos os detalhes para: {instance_ids}...")
            instance_details_map = self._get_instance_details(session, instance_ids)

            fleet_vms = []
            for instance_id, details in instance_details_map.items():
                price = 0
                for inst in instances:
                    if inst.instance_type == details['instance_type']:
                        price = inst.price
                spec = FleetVmSpec(
                    provider='aws',
                    instance_id=instance_id,
                    instance_type=details['instance_type'],
                    region_az=details['region_az'],
                    price=price,
                    public_ip=details['public_ip'],
                    private_ip=details['private_ip'],
                )
                fleet_vms.append(spec)
            
            logging.info(f"{len(fleet_vms)} instâncias da frota {fleet_id} foram formatadas com sucesso.")

            self.FLEET_NUM += 1
            return fleet_name, fleet_vms, errors

        except Exception as e:
            logging.error(f"Falha no processo de criação da frota: {e}")
            return None, None, None


    def delete_fleet(self):
        self._delete_command('sa-east-1')
        self._delete_command('us-east-1')


    def _delete_command(self, region, tag='MultiCloud'):
        command = f'aws ec2 describe-instances --region {region} --filters "Name=tag:Name,Values={tag}" "Name=instance-state-name,Values=running" --query "Reservations[*].Instances[*].InstanceId" --output text'
        session = boto3.Session(region_name=region)
        ec2_client = session.client("ec2")

        try:
            result = subprocess.run(command, shell=True, check=True, capture_output=True)
            input_string = result.stdout.decode() if isinstance(result.stdout, bytes) else str(result.stdout)
            instances_ids = re.findall(r'\bi-[0-9a-f]{17}\b', input_string)

            if(instances_ids):
                print(f"Terminating {len(instances_ids)} instances...")
                response = ec2_client.terminate_instances(
                    InstanceIds=instances_ids,
                )
                print(f"{len(instances_ids)} instances terminated")


            else:
                print(f'No running instances found.')
            
        except subprocess.CalledProcessError as e:
            print(f"Error executing command: {e}")
    

    def _instance_template_config(self, instances):
        with open('caminho/vm_catalog.yaml', 'r') as f: 
            data = yaml.safe_load(f)

        overrides = []

        for inst in instances:
            instance_type = inst.instance_type
            subnet_id = data['providers']['aws']['regions'][inst.region]['availability_zones'][inst.region_az]
            overrides.append({
                'InstanceType': instance_type,
                'SubnetId': subnet_id
            })

        return overrides
    
   
    def _get_instance_details(self, session, instance_ids):
        if not instance_ids:
            return {}

        ec2_client = session.client("ec2")
        details_map = {}

        try:
            response = ec2_client.describe_instances(InstanceIds=instance_ids)
            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    instance_id = instance['InstanceId']
                    
                    details_map[instance_id] = {
                        'instance_type': instance.get('InstanceType', 'N/A'),
                        'region_az': instance.get('Placement', {}).get('AvailabilityZone', 'N/A'),
                        'public_ip': instance.get('PublicIpAddress', 'N/A'),
                        'private_ip': instance.get('PrivateIpAddress', 'N/A'),
                        'status': instance.get('State', {}).get('Name', 'unknown')
                    }
        except Exception as e:
            logging.error(f"Erro ao chamar describe_instances: {e}")
            return details_map

        return details_map
    
