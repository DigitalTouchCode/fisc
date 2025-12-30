fiscal_id = 23444
fiscal_day = 1
taxes = [
    {"name": "standard 15.5%", "percent": 15.5},
    {"name": "exmpt", "percent": 0},
    {"name": "zero rated 0", "percent": 15.5},
]
fiscal_counters = [
    {
        "name": "SALEBYTAX",
        "tax_name": "standard 15%",
        "tax_percent": 15.5,
        "value": 20.00,
    },
    {
        "name": "SALEBYTAXBYTAX",
        "tax_name": "standard 15%",
        "tax_percent": 15.5,
        "tax_value": 11.10,
        "value": 20.00,
    },
    {"name": "BALANCEBYMONEYTYPE", "type": "CASH", "value": 20.00},
]


def close_day():
    tax_map = {tax["name"]: tax["percent"] for tax in taxes}
    """
        1. if exempt skip counter
        2. if standard get counter 
        3. 23444129-12-12:03SALEBYTAXBYTAX15.502000SALEBYTAXBYAX15.501110BALANCEBYMONEYTYPECASH2000
        4. take fiscal counters as db objects filter by fiscal_counter_name and tax_name
    """

    salebytax_string = ""
    total_value = 0
    total_taxes_value = 0

    for counter in fiscal_counters:

        if counter.get("name") == "SALEBYTAXBYTAX":
            total_taxes_value += counter.get("value")


def salebytax(counter):
    if (
        counter.get("name") == "SALEBYTAX"
        and counter.get("tax_name").lower() == "standard 15%"
    ):
        total_line_value += counter.get("value")

    if (
        counter.get("name") == "SALEBYTAX"
        and counter.get("tax_name").lower() == "exempt"
    ):
        total_line_value += counter.get("value")

    else:
        total_line_value += counter.get("value")


if __name__ == "__main__":
    close_day()
