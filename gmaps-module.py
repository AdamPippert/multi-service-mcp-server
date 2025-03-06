# tools/gmaps_tool.py
from flask import Blueprint, request, jsonify, current_app
import requests

gmaps_routes = Blueprint('gmaps', __name__)

def handle_action(action, parameters):
    """Handle Google Maps tool actions according to MCP standard"""
    action_handlers = {
        "geocode": geocode,
        "reverseGeocode": reverse_geocode,
        "getDirections": get_directions,
        "searchPlaces": search_places,
        "getPlaceDetails": get_place_details
    }
    
    if action not in action_handlers:
        raise ValueError(f"Unknown action: {action}")
    
    return action_handlers[action](parameters)

def geocode(parameters):
    """Convert an address to geographic coordinates"""
    address = parameters.get('address')
    
    if not address:
        raise ValueError("Address parameter is required")
    
    params = {
        'address': address,
        'key': current_app.config['GMAPS_API_KEY']
    }
    
    response = requests.get('https://maps.googleapis.com/maps/api/geocode/json', params=params)
    
    if response.status_code != 200:
        raise Exception(f"Google Maps API error: {response.json()}")
    
    return response.json()

def reverse_geocode(parameters):
    """Convert geographic coordinates to an address"""
    lat = parameters.get('lat')
    lng = parameters.get('lng')
    
    if not lat or not lng:
        raise ValueError("Latitude and longitude parameters are required")
    
    params = {
        'latlng': f'{lat},{lng}',
        'key': current_app.config['GMAPS_API_KEY']
    }
    
    response = requests.get('https://maps.googleapis.com/maps/api/geocode/json', params=params)
    
    if response.status_code != 200:
        raise Exception(f"Google Maps API error: {response.json()}")
    
    return response.json()

def get_directions(parameters):
    """Get directions between two locations"""
    origin = parameters.get('origin')
    destination = parameters.get('destination')
    mode = parameters.get('mode', 'driving')
    
    if not origin or not destination:
        raise ValueError("Origin and destination parameters are required")
    
    params = {
        'origin': origin,
        'destination': destination,
        'mode': mode,
        'key': current_app.config['GMAPS_API_KEY']
    }
    
    response = requests.get('https://maps.googleapis.com/maps/api/directions/json', params=params)
    
    if response.status_code != 200:
        raise Exception(f"Google Maps API error: {response.json()}")
    
    return response.json()

def search_places(parameters):
    """Search for places using the Google Places API"""
    query = parameters.get('query')
    location = parameters.get('location')
    radius = parameters.get('radius', 1000)
    place_type = parameters.get('type')
    
    if not query and not (location and place_type):
        raise ValueError("Either query or location with type parameters are required")
    
    params = {
        'key': current_app.config['GMAPS_API_KEY']
    }
    
    if query:
        params['query'] = query
        url = 'https://maps.googleapis.com/maps/api/place/textsearch/json'
    else:
        params['location'] = location
        params['radius'] = radius
        params['type'] = place_type
        url = 'https://maps.googleapis.com/maps/api/place/nearbysearch/json'
    
    response = requests.get(url, params=params)
    
    if response.status_code != 200:
        raise Exception(f"Google Maps API error: {response.json()}")
    
    return response.json()

def get_place_details(parameters):
    """Get details for a specific place"""
    place_id = parameters.get('placeId')
    
    if not place_id:
        raise ValueError("Place ID parameter is required")
    
    params = {
        'place_id': place_id,
        'fields': 'name,rating,formatted_address,geometry,photo,opening_hours,price_level,website,formatted_phone_number',
        'key': current_app.config['GMAPS_API_KEY']
    }
    
    response = requests.get('https://maps.googleapis.com/maps/api/place/details/json', params=params)
    
    if response.status_code != 200:
        raise Exception(f"Google Maps API error: {response.json()}")
    
    return response.json()

# API routes for direct access (not through MCP gateway)
@gmaps_routes.route('/geocode', methods=['GET'])
def api_geocode():
    """API endpoint for geocoding an address"""
    try:
        address = request.args.get('address')
        result = geocode({'address': address})
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@gmaps_routes.route('/reverseGeocode', methods=['GET'])
def api_reverse_geocode():
    """API endpoint for reverse geocoding coordinates"""
    try:
        lat = request.args.get('lat')
        lng = request.args.get('lng')
        result = reverse_geocode({'lat': lat, 'lng': lng})
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@gmaps_routes.route('/getDirections', methods=['GET'])
def api_get_directions():
    """API endpoint for getting directions"""
    try:
        origin = request.args.get('origin')
        destination = request.args.get('destination')
        mode = request.args.get('mode', 'driving')
        result = get_directions({'origin': origin, 'destination': destination, 'mode': mode})
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@gmaps_routes.route('/searchPlaces', methods=['GET'])
def api_search_places():
    """API endpoint for searching places"""
    try:
        parameters = {
            'query': request.args.get('query'),
            'location': request.args.get('location'),
            'radius': request.args.get('radius', 1000),
            'type': request.args.get('type')
        }
        result = search_places(parameters)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@gmaps_routes.route('/getPlaceDetails', methods=['GET'])
def api_get_place_details():
    """API endpoint for getting place details"""
    try:
        place_id = request.args.get('placeId')
        result = get_place_details({'placeId': place_id})
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 400
