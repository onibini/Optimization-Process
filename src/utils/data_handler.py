import csv
import os

def load_env_data(site_id, filepath=r'data\env_data.csv'):
    '''
    env_data.csv 파일에서 특정 SIteID의 해양 환경 데이터를 읽어옴
    '''
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Environment data file not found: {filepath}")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if int(row['SiteID']) == site_id:
                return {
                    'SiteName': row['SiteName'],
                    'Hs': float(row['Hs']),
                    'Tp': float(row['Tp']),
                    'Gamma': float(row['Gamma']),
                    'Depth': float(row['Depth'])
                }
    raise ValueError(f"SiteID '{site_id}' not found in environment data.")