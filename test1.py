import requests

with open(r"C:\Users\Bruno\Desktop\api-tg\api-dash-tg\SUPER-OVER.xlsx", "rb") as f:
    r = requests.post(
        "https://api-esoccer.arvsystems.cloud/analyze",
        headers={"X-API-Key": "hWvCtrECTKR9GbAZJWk2k5zvjC2cQbm2"},
        data={"strategy": "Over/HT \u2014 Dupla + Linha"},
        files={"files": f},
        timeout=30,
    )
print(r.status_code)
print(r.json())
