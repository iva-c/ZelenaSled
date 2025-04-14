from django.apps import AppConfig
import zipfile
import os

class RoutingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'routing'

    def ready(self):
        self.unzip_json_file()

    def unzip_json_file(self):
        '''Unzip large JSON file when starting the server'''
        
        zip_file_path = os.path.join(self.path, 'data', 'avg_ndvi_h3_13.zip')
        extracted_file_path = os.path.join(self.path, 'data', 'avg_ndvi_h3_13.json')

        # Only unzip if the JSON file doesn't already exist
        if not os.path.exists(extracted_file_path):
            with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
                zip_ref.extract('avg_ndvi_h3_13.json', os.path.dirname(extracted_file_path))
            print(f"Unzipped {zip_file_path} to {extracted_file_path}")
        else:
            print(f"JSON file already extracted: {extracted_file_path}")

        zip_file_path = os.path.join(self.path, 'data', 'heat_h3.zip')
        extracted_file_path = os.path.join(self.path, 'data', 'heat_h3.json')

        # Only unzip if the JSON file doesn't already exist
        if not os.path.exists(extracted_file_path):
            with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
                zip_ref.extract('heat_h3.json', os.path.dirname(extracted_file_path))
            print(f"Unzipped {zip_file_path} to {extracted_file_path}")
        else:
            print(f"JSON file already extracted: {extracted_file_path}")

