from .providers.aws_provider import AWSProvider
from .providers.azure_provider import AzureProvider

class CloudProviderFactory:
    @staticmethod
    def get_provider(provider_name: str):
        if provider_name.lower() == "aws":
            return AWSProvider()
        elif provider_name.lower() == "azure":
            return AzureProvider()
        else:
            raise ValueError(f"Provider '{provider_name}' não suportado.")