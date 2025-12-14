import logging
import time

from ...core.models import FleetVmSpec
from ..abstract_factory import AbstractCloudProvider
from azure.identity import DefaultAzureCredential
from azure.mgmt.computefleet import ComputeFleetMgmtClient # type: ignore
from azure.mgmt.compute import ComputeManagementClient # type: ignore
from azure.mgmt.network import NetworkManagementClient # type: ignore
from azure.core.exceptions import ResourceNotFoundError, HttpResponseError

class AzureProvider(AbstractCloudProvider):
    FLEET_NUM = 1
    SUBSCRIPTION_ID = 'SUBSCRIPTION_ID'
    RESOURCE_GROUP_NAME = 'RESOURCE_GROUP_NAME'
    ADMIN_USERNAME = "admin"
    ADMIN_PASSWORD = "admin"
    FLEET_NAME = f'AZURE-FLEET'

    credential = DefaultAzureCredential()
    fleet_client = ComputeFleetMgmtClient(credential, SUBSCRIPTION_ID)
    compute_client = ComputeManagementClient(credential, SUBSCRIPTION_ID)
    network_client = NetworkManagementClient(credential, SUBSCRIPTION_ID)

    fleet_names = []

    def get_all_vms(self, provider_config, vcpus, location):
        LOCATION_MAP = {
            'br': ['brazilsouth'],
        }

        all_provider_regions = provider_config.get('regions', {})
        
        target_region_names = LOCATION_MAP.get('br')

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
                'provider': 'azure',
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
    

    def create_fleet(self, instances, allocation_strategy, target_capacity, tag='MultiCloud'):
        if allocation_strategy == 'lowest-price':
            allocation_strategy = 'LowestPrice'
        elif allocation_strategy == 'capacity-optimized':
            allocation_strategy = "CapacityOptimized"
        elif allocation_strategy == 'price-capacity-optimized':
            allocation_strategy = 'PriceCapacityOptimized'

        region = instances[0].region
        if region == 'eastus':
            return None, [], []
        
        overrides = self._instance_template_config(instances)

        fleet_parameters = {
            "location": region,
            "properties": {
                "vmSizesProfile": overrides[:10],
                "computeProfile": {
                    "baseVirtualMachineProfile": {
                        "networkProfile": {
                            "networkApiVersion": "2024-10-01",
                            "networkInterfaceConfigurations": [
                                {
                                    "name": "vnet-brazilsouth-1-nic01",
                                    "properties": {
                                        "primary": True,
                                        "enableAcceleratedNetworking": False,
                                        "networkSecurityGroup": {
                                            "id": "id"
                                        },
                                        "ipConfigurations": [
                                            {
                                                "name": "vnet-brazilsouth-1-nic01-publicip-ipConfig",
                                                "properties": {
                                                    "primary": True,
                                                    "subnet": {
                                                        "id": "id"
                                                    },
                                                    "publicIPAddressConfiguration": {
                                                        "name": "vnet-brazilsouth-1-nic01-publicip",
                                                        "properties": {
                                                            "idleTimeoutInMinutes": 15
                                                        }
                                                    }
                                                }
                                            }
                                        ]
                                    }
                                }
                            ]
                        },
                        "osProfile": {
                            "adminUsername": "admin",
                            "computerNamePrefix": "prefix",
                            "linuxConfiguration": {
                                "disablePasswordAuthentication": True,
                                "ssh": {
                                    "publicKeys": [
                                        {
                                            "path": "path",
                                            "keyData": ""
                                        }
                                    ]
                                }
                            }
                        },
                        "storageProfile": {
                            "imageReference": {
                                "offer": "0001-com-ubuntu-server-focal",
                                "publisher": "canonical",
                                "sku": "20_04-lts-gen2",
                                "version": "latest",
                            },
                            "osDisk": {
                                "caching": "ReadWrite",
                                "createOption": "FromImage",
                                "managedDisk": {"storageAccountType": "Standard_LRS"},
                                "osType": "Linux",
                            },
                        },
                    },
                    "computeApiVersion": "2023-09-01",
                    "platformFaultDomainCount": 1,
                },
                "regularPriorityProfile": {"capacity": 0},
                "spotPriorityProfile": {
                    "allocationStrategy": "LowestPrice",
                    "capacity": target_capacity,
                    "evictionPolicy": "Delete",
                },
            },
            "tags": {"key": tag}
        }

        try:
            fleet_name = f'{self.FLEET_NAME}-{self.FLEET_NUM}'
            logging.info(f"Iniciando criação da frota '{fleet_name}' no Azure...")

            
            try:
                poller = self.fleet_client.fleets.begin_create_or_update(
                    self.RESOURCE_GROUP_NAME, 
                    fleet_name, 
                    fleet_parameters
                )
                fleet_result = poller.result()
                logging.info(f"Frota '{fleet_name}' provisionada com sucesso.")
            except Exception as e:
                logging.warning(f"Falha parcial na frota '{fleet_name}': {e.message}")


            self.fleet_names.append(fleet_name)
            logging.info(f"Frota '{fleet_name}' provisionada. Buscando VMs associadas...")

            instance_details_map = self._get_azure_vm_details(tag, fleet_name)
            
            fleet_vms = []

            for vm_name, details in instance_details_map.items():
                price = 0
                for inst in instances:
                    instance_type = inst.instance_type
                    instance_type = instance_type.replace(" ", "_")
                    instance_type = 'Standard_' + instance_type
                    if instance_type == details['instance_type']:
                        price = inst.price

                fleet_vms.append(
                    FleetVmSpec(
                        provider='azure',
                        instance_id=details['instance_id'],
                        instance_type=details['instance_type'],
                        region_az=details['region_az'],
                        price=price,
                        public_ip=details['public_ip'],
                        private_ip=details['private_ip'],
                    )
                )

    
            
            self.FLEET_NUM += 1
            return fleet_name, fleet_vms, [] 

        except Exception as e:
            return None, [], []

    

    def delete_fleet(self):
        for fleet_name in self.fleet_names:
            response = self.fleet_client.fleets.begin_delete(
                resource_group_name=self.RESOURCE_GROUP_NAME,
                fleet_name=fleet_name,
            ).result()
            logging.info(f'{fleet_name} deletada com sucesso...')
        logging.info(f'{len(self.fleet_names)} Fleets deletadas com sucesso!')
        self.fleet_names.clear()



    def _get_azure_vm_details(self, tag, fleet_name):
        vms = self.compute_client.virtual_machines.list_all()
        details_map = {}

        for vm in vms:
            vm_tags = vm.tags or {}
            rg = self.RESOURCE_GROUP_NAME.upper()  
            
            if vm_tags.get("key") == tag and fleet_name in vm.name:
                vm_name = vm.name

                try:
                    nic_id = vm.network_profile.network_interfaces[0].id
                    nic_name = nic_id.split("/")[-1]
                    nic = self.network_client.network_interfaces.get(rg, nic_name)

                    ip_config = nic.ip_configurations[0]
                    private_ip = ip_config.private_ip_address

                    public_ip = None
                    if ip_config.public_ip_address:
                        pip_id = ip_config.public_ip_address.id
                        pip_name = pip_id.split("/")[-1]
                        try:
                            pip = self.network_client.public_ip_addresses.get(rg, pip_name)
                            public_ip = pip.ip_address
                        except ResourceNotFoundError:
                            logging.warning(f"Public IP {pip_name} não encontrado para VM {vm_name}")

                    details_map[vm_name] = {
                        "instance_type": vm.hardware_profile.vm_size,
                        "region_az": f"{vm.location}-{vm.zones[0] if vm.zones else '1'}",
                        "public_ip": public_ip,
                        "private_ip": private_ip,
                        "instance_id": vm.vm_id,
                    }

                except (IndexError, ResourceNotFoundError, HttpResponseError) as e:
                    continue

        return details_map



    def _instance_template_config(self, instances):
        overrides = []

        for inst in instances:
            instance_type = inst.instance_type
            instance_type = instance_type.replace(" ", "_")
            instance_type = 'Standard_' + instance_type
            overrides.append({"name": instance_type})

        return overrides
    
