# English filename: sdv_prepare_your_own_data_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/16일차 AI 가이드라인 설명과 실습/가이드A-1. 개인정보/SDV_Prepare_your_own_data.py
# Original filename: SDV_Prepare_your_own_data.py

# ---- Cell ----
%pip install sdv
# 설치 이후 다시시작 해주세요.

# ---- Cell ----
 from google.colab import files

# Optional: You can skip this step if you are running the code on your own
# machine
# uploaded = files.upload()

# ---- Cell ----
from sdv.datasets.local import load_csvs
from sdv.datasets.demo import download_demo

# This is the default folder name that the GOogle Colab notebook uses.
# Change this if you have your own folder with CSV files.
FOLDER_NAME = 'content/'

try:
  datasets = load_csvs(folder_name='/content/')
except ValueError:
  print('You have not uploaded any csv files. Using some demo data instead.')
  datasets, _ = download_demo(
    modality='multi_table',
    dataset_name='fake_hotels'
  )

# ---- Cell ----
datasets.keys()

# ---- Cell ----
hotels_table = datasets['hotels']

# use the head method to inspect the first few rows of the data
hotels_table.head(3)

# ---- Cell ----
guests_table = datasets['guests']

guests_table.head(3)

# ---- Cell ----
from sdv.metadata import MultiTableMetadata

metadata = MultiTableMetadata()

# ---- Cell ----
metadata.detect_table_from_dataframe(
    table_name='guests',
    data=guests_table
)

metadata.detect_table_from_dataframe(
    table_name='hotels',
    data=hotels_table
)

# ---- Cell ----
print('Auto detected data:\n')
metadata

# ---- Cell ----
metadata.update_column(
    table_name='guests',
    column_name='checkin_date',
    sdtype='datetime',
    datetime_format='%d %b %Y'
)

metadata.update_column(
    table_name='guests',
    column_name='checkout_date',
    sdtype='datetime',
    datetime_format='%d %b %Y'
)

# ---- Cell ----
metadata.update_column(
    table_name='hotels',
    column_name='hotel_id',
    sdtype='id',
    regex_format='HID_[0-9]{3,4}'
)

metadata.update_column(
    table_name='guests',
    column_name='hotel_id',
    sdtype='id',
    regex_format='HID_[0-9]{3,4}'
)

# ---- Cell ----
metadata.update_column(
    table_name='guests',
    column_name='guest_email',
    sdtype='email',
    pii=True
)

metadata.update_column(
    table_name='guests',
    column_name='billing_address',
    sdtype='address',
    pii=True
)

metadata.update_column(
    table_name='guests',
    column_name='credit_card_number',
    sdtype='credit_card_number',
    pii=True
)

# ---- Cell ----
metadata.set_primary_key(
    table_name='hotels',
    column_name='hotel_id'
)

metadata.set_primary_key(
    table_name='guests',
    column_name='guest_email'
)

# ---- Cell ----
metadata.add_alternate_keys(
    table_name='guests',
    column_names=['credit_card_number']
)

# ---- Cell ----
metadata.add_relationship(
    parent_table_name='hotels',
    child_table_name='guests',
    parent_primary_key='hotel_id',
    child_foreign_key='hotel_id'
)

# ---- Cell ----
metadata.validate()

# ---- Cell ----
metadata.visualize()

# ---- Cell ----
metadata.save_to_json('metadata.json')

metadata = MultiTableMetadata.load_from_json('metadata.json')

# ---- Cell ----
from sdv.multi_table import HMASynthesizer

synthesizer = HMASynthesizer(metadata)
synthesizer.validate(datasets)

# ---- Cell ----
synthesizer.fit(datasets)
synthetic_data = synthesizer.sample(scale=1)

# ---- Cell ----
synthetic_data['guests'].head(3)
