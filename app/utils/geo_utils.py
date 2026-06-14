from math import radians, sin, cos, sqrt, atan2


def calculate_distance_meters(lat1, lon1, lat2, lon2):
    earth_radius = 6371000  # meters

    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)

    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    )

    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return earth_radius * c