from abc import ABC, abstractmethod

class AbstractCloudProvider(ABC):

    @abstractmethod
    def create_fleet(self):
        pass
    
    @abstractmethod
    def delete_fleet(self):
        pass

    @abstractmethod
    def get_all_vms(self):
        pass