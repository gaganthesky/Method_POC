## Integration Guide

URL : https://methodfi.notion.site/Citi-Development-Integration-Guide-3187b5a59a6d80c3ace7d2224816589d


## Verifying access

``` bash

curl https://dev.methodfi.com/ping \
  -H "Method-Version: 2024-07-04" \
  -H "Authorization: Bearer {API_KEY}"

```


## Create Entity

``` bash

curl https://dev.methodfi.com/ \
-X POST \
-H "Authorization: Bearer {API_KEY}" \
-H "Method-Version: 2024-07-04" \
-H "Content-Type: application/json" \
-d '{
  "type": "individual",
  "individual": {
    "first_name": "Kevin",
    "last_name": "Doyle",
    "phone": "+15121231113",
    "email": "kevin.doyle@gmail.com",
    "dob": "1997-03-18",
    "ssn": "123456789"
  },
  "address": {
    "line1": "3300 N Interstate 35",
    "line2": null,
    "city": "Austin",
    "state": "TX",
    "zip": "78705"
  }
}'
```