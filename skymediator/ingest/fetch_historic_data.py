"""
Historic Datasets Downloader and Parser for Kempegowda International Airport (VOBL / BLR).
Fetches real historical METAR observations from the Iowa Environmental Mesonet (IEM) ASOS archive,
converts meteorological features, and seeds the historical database for ML training and evaluation.
"""

from ingest.fetch_historic_data import (
    HISTORICAL_DATA_DIR,
    HISTORICAL_METAR_CSV,
    HISTORICAL_ROUTES_CSV,
    ensure_dirs,
    download_historical_metar,
    parse_and_save_historical_metar,
    seed_historical_flight_performance_routes,
    seed_db_with_historical_weather,
    main
)

if __name__ == "__main__":
    main()
