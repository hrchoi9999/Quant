# English filename: sdv_synthesize_sequences_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/16일차 AI 가이드라인 설명과 실습/가이드A-1. 개인정보/SDV_Synthesize_Sequences_(PAR).py
# Original filename: SDV_Synthesize_Sequences_(PAR).py

# ---- Cell ----
%pip install sdv
# 설치 이후 다시시작 해주세요.

# ---- Cell ----
from sdv.datasets.demo import download_demo

real_data, metadata = download_demo(
    modality='sequential',
    dataset_name='nasdaq100_2019'
)

# ---- Cell ----
real_data.head()

# ---- Cell ----
metadata

# ---- Cell ----
amzn_sequence = real_data[real_data['Symbol'] == 'AMZN']
amzn_sequence

# ---- Cell ----
real_data['Symbol'].unique()

# ---- Cell ----
real_data[real_data['Symbol'] == 'AMZN']['Sector'].unique()

# ---- Cell ----
from sdv.sequential import PARSynthesizer

synthesizer = PARSynthesizer(
    metadata,
    context_columns=['Sector', 'Industry'])

synthesizer.fit(real_data)
# 여기서 에러가 난다면 다시시작해서 실행해 주세요

# ---- Cell ----
synthetic_data = synthesizer.sample(num_sequences=10)
synthetic_data.head()

# ---- Cell ----
synthetic_data[['Symbol', 'Industry']].groupby(['Symbol']).first().reset_index()

# ---- Cell ----
synthesizer.save('my_synthesizer.pkl')

synthesizer = PARSynthesizer.load('my_synthesizer.pkl')

# ---- Cell ----
custom_synthesizer = PARSynthesizer(
    metadata,
    epochs=25,
    context_columns=['Sector', 'Industry'],
    verbose=True)

custom_synthesizer.fit(real_data)

# ---- Cell ----
custom_synthesizer.sample(num_sequences=3, sequence_length=2)

# ---- Cell ----
import pandas as pd

scenario_context = pd.DataFrame(data={
    'Symbol': ['COMPANY-A', 'COMPANY-B', 'COMPANY-C', 'COMPANY-D', 'COMPANY-E'],
    'Sector': ['Technology']*2 + ['Consumer Services']*3,
    'Industry': ['Computer Manufacturing', 'Computer Software: Prepackaged Software',
                 'Hotels/Resorts', 'Restaurants', 'Clothing/Shoe/Accessory Stores']
})

scenario_context

# ---- Cell ----
custom_synthesizer.sample_sequential_columns(
    context_columns=scenario_context,
    sequence_length=2
)

# ---- Cell ----

