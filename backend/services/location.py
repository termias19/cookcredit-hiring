"""Google area lookup and short-lived, user-bound search locations.

No Google response or customer device location is written to the database.
Search tokens travel in POST bodies, never URL parameters or request logs.
"""
import math
import os
import re
import requests
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired


class LocationUnavailable(Exception):
    pass


def coordinates(lat, lng):
    if (isinstance(lat, bool) or isinstance(lng, bool)
            or not isinstance(lat, (int, float)) or not isinstance(lng, (int, float))
            or not math.isfinite(lat) or not math.isfinite(lng)
            or not -90 <= lat <= 90 or not -180 <= lng <= 180):
        raise ValueError('Invalid coordinates')
    return float(lat), float(lng)


def _serializer():
    secret = os.environ.get('LOCATION_TOKEN_SECRET') or os.environ.get('SECRET_KEY', '')
    if len(secret) < 32:
        raise LocationUnavailable('Location signing is not configured')
    return URLSafeTimedSerializer(secret, salt='cookcredit-location-v1')


def search_token(*, user_id, lat, lng):
    lat, lng = coordinates(lat, lng)
    return _serializer().dumps({'uid': user_id, 'lat': lat, 'lng': lng})


def read_search_token(token, user_id):
    if not isinstance(token, str) or len(token) > 2048:
        raise ValueError('Invalid location token')
    try:
        payload = _serializer().loads(token, max_age=1800)
    except (BadSignature, SignatureExpired) as exc:
        raise ValueError('Location expired. Choose your area again.') from exc
    if not isinstance(payload, dict) or payload.get('uid') != user_id:
        raise ValueError('Invalid location token')
    return coordinates(payload.get('lat'), payload.get('lng'))


def resolve_area(body, user_id):
    if not isinstance(body, dict) or set(body) - {'postalCode', 'lat', 'lng', 'accuracyMeters', 'language'}:
        raise ValueError('Invalid location request')
    key = os.environ.get('GOOGLE_GEOCODING_API_KEY', '')
    if not key:
        raise LocationUnavailable('Area lookup is not configured')
    _serializer()  # Validate signing before making a billable Google request.
    postal = body.get('postalCode')
    language = 'es' if body.get('language') == 'ES' else 'en'
    query = {'key': key, 'language': language}
    accuracy = None
    if postal is not None:
        if not isinstance(postal, str) or not re.fullmatch(r'\d{5}', postal):
            raise ValueError('Enter a five-digit US ZIP code')
        if 'lat' in body or 'lng' in body:
            raise ValueError('Choose ZIP code or device location')
        query['components'] = f'postal_code:{postal}|country:US'
    else:
        lat, lng = coordinates(body.get('lat'), body.get('lng'))
        accuracy = body.get('accuracyMeters')
        if (not isinstance(accuracy, (int, float)) or isinstance(accuracy, bool)
                or not math.isfinite(accuracy) or not 0 <= accuracy <= 100000):
            raise ValueError('Invalid location accuracy')
        query.update(latlng=f'{lat},{lng}', result_type='postal_code')
    try:
        response = requests.get('https://maps.googleapis.com/maps/api/geocode/json',
            params=query, timeout=(3, 8), allow_redirects=False)
        if response.status_code != 200:
            raise LocationUnavailable('Area lookup unavailable')
        payload = response.json()
    except (requests.RequestException, ValueError):
        raise LocationUnavailable('Area lookup unavailable') from None
    if not isinstance(payload, dict):
        raise LocationUnavailable('Area lookup unavailable')
    if payload.get('status') == 'ZERO_RESULTS':
        raise LookupError('Area not found')
    if payload.get('status') != 'OK':
        # Google error messages can include account details; never expose them.
        raise LocationUnavailable('Area lookup unavailable')
    selected = None
    for result in payload.get('results', []):
        parts = {kind: part for part in result.get('address_components', []) for kind in part.get('types', [])}
        found_zip = parts.get('postal_code', {}).get('long_name')
        if (parts.get('country', {}).get('short_name') == 'US'
                and found_zip and (postal is None or found_zip == postal)
                and not result.get('partial_match')):
            selected = (result, parts, found_zip)
            break
    if selected is None:
        raise LookupError('Area not found')
    result, parts, found_zip = selected
    if postal is not None:
        point = (result.get('geometry') or {}).get('location') or {}
        try:
            lat, lng = coordinates(point.get('lat'), point.get('lng'))
        except ValueError:
            raise LocationUnavailable('Area lookup unavailable') from None
    city = (parts.get('locality') or parts.get('postal_town') or parts.get('administrative_area_level_2') or {}).get('long_name', '')
    state = parts.get('administrative_area_level_1', {}).get('short_name', '')
    return {'postalCode': found_zip, 'city': city, 'state': state,
            'label': ', '.join(x for x in (city, state) if x),
            'source': 'zip' if postal is not None else 'device', 'accuracyMeters': accuracy,
            'provider': 'Google Maps', 'expiresInSeconds': 1800,
            'locationToken': search_token(user_id=user_id, lat=lat, lng=lng)}
