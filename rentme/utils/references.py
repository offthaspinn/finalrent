import random
import string

def generate_property_ref(length=2):
    return "".join(random.choices(string.ascii_uppercase, k=length))

def generate_unit_reference(property_ref: str, unit_no: str) -> str:
    return f"{property_ref}{unit_no}"
