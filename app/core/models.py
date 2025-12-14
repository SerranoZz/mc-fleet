from dataclasses import dataclass

@dataclass
class VMSpec:
    provider: str
    instance_type: str
    region: str
    region_az: str
    price: float

    def to_dict(self):
        return self.__dict__


@dataclass
class FleetVmSpec:
    provider: str
    instance_type: str
    instance_id: str
    region_az: str
    price: float
    public_ip: str
    private_ip: str

    def to_dict(self):
        return self.__dict__
