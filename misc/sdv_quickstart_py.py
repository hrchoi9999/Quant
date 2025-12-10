# English filename: sdv_quickstart_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/16일차 AI 가이드라인 설명과 실습/가이드A-1. 개인정보/SDV_Quickstart .py
# Original filename: SDV_Quickstart .py

# ---- Cell ----
%pip install sdv

# ---- Cell ----
from sdv.datasets.demo import download_demo

real_data, metadata = download_demo(
    modality='single_table',
    dataset_name='fake_hotel_guests'
)

# ---- Cell ----
real_data.head()

# ---- Cell ----
metadata

# ---- Cell ----
from sdv.lite import SingleTablePreset

synthesizer = SingleTablePreset(
    metadata,
    name='FAST_ML'
)

# ---- Cell ----
synthesizer.fit(
    data=real_data
)
# 에러나면 다시시작 실행

# ---- Cell ----
synthetic_data = synthesizer.sample(
    num_rows=500
)

synthetic_data.head()

# ---- Cell ----
sensitive_column_names = ['guest_email', 'billing_address', 'credit_card_number']

real_data[sensitive_column_names].head(3)

# ---- Cell ----
synthetic_data[sensitive_column_names].head(3)

# ---- Cell ----
from sdv.evaluation.single_table import evaluate_quality

quality_report = evaluate_quality(
    real_data,
    synthetic_data,
    metadata
)

# ---- Cell ----
quality_report.get_visualization('Column Shapes')

# ---- Cell ----
from sdv.evaluation.single_table import get_column_plot

fig = get_column_plot(
    real_data=real_data,
    synthetic_data=synthetic_data,
    column_name='amenities_fee',
    metadata=metadata
)

fig.show()

# ---- Cell ----
from sdv.evaluation.single_table import get_column_pair_plot

fig = get_column_pair_plot(
    real_data=real_data,
    synthetic_data=synthetic_data,
    column_names=['checkin_date', 'checkout_date'],
    metadata=metadata
)

fig.show()

# ---- Cell ----
synthesizer.save('my_synthesizer.pkl')

synthesizer = SingleTablePreset.load('my_synthesizer.pkl')
