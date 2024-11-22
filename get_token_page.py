import requests

user_access_token = 'EAARQng7HXUwBOZCBtZAnkZCJOc6129hvFPZAb6eII8fEtN6f2eJ96MtlZBhV0FZCZB0L0AESr1lo06ls24FvZB0hWsh72WZB5u9SsuRQiByHF7WySgOky6BRfCy0RgbgtpKpFfXOwzihMfjMwbqYlA0hxmltoGDAFnDIZALHssiOyr9LHH19SqIZA0h1ZCJrEJRPnGmm1JDsu68fHgqbCks27hMYFp1JwlwZD'

url = 'https://graph.facebook.com/v17.0/me/accounts'

params = {
    'access_token': user_access_token
}

response = requests.get(url, params=params)
data = response.json()

if 'error' in data:
    print('Ошибка при получении списка страниц:', data['error'])
else:
    # Найдите вашу страницу и получите ее токен доступа
    for page in data.get('data', []):
        page_access_token = page['access_token']
        page_id = page['id']
        print('Токен доступа страницы:', page_access_token)
        print('ID страницы:', page_id)
        break
