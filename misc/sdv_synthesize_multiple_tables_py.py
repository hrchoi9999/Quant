# English filename: sdv_synthesize_multiple_tables_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/16일차 AI 가이드라인 설명과 실습/가이드A-1. 개인정보/SDV_Synthesize_multiple_tables_(HMA).py
# Original filename: SDV_Synthesize_multiple_tables_(HMA).py

# ---- Cell ----
%pip install sdv

# ---- Cell ----
from sdv.datasets.demo import download_demo

real_data, metadata = download_demo(
    modality='multi_table',
    dataset_name='fake_hotels'
)

# ---- Cell ----
real_data['hotels'].head(3)

# ---- Cell ----
real_data['guests'].head(3)

# ---- Cell ----
metadata.visualize()

# ---- Cell ----
from sdv.multi_table import HMASynthesizer

synthesizer = HMASynthesizer(metadata)
synthesizer.fit(real_data)

# ---- Cell ----
synthetic_data = synthesizer.sample(scale=2)

# ---- Cell ----
synthetic_data['hotels'].head(3)

# ---- Cell ----
synthetic_data['guests'].head(3)

# ---- Cell ----
sensitive_columns = ['guest_email', 'billing_address', 'credit_card_number']
real_data['guests'][sensitive_columns].head()

# ---- Cell ----
synthetic_data['guests'][sensitive_columns].head()

# ---- Cell ----
from sdv.evaluation.multi_table import evaluate_quality

quality_report = evaluate_quality(
    real_data,
    synthetic_data,
    metadata,
    verbose=False
)

# ---- Cell ----
fig = quality_report.get_visualization('Column Shapes', table_name='guests')
fig.show()

# ---- Cell ----
from sdv.evaluation.multi_table import get_column_plot

fig = get_column_plot(
    real_data=real_data,
    synthetic_data=synthetic_data,
    column_name='has_rewards',
    table_name='guests',
    metadata=metadata
)

fig.show()

# ---- Cell ----
from sdv.evaluation.multi_table import get_column_pair_plot

fig = get_column_pair_plot(
    real_data=real_data,
    synthetic_data=synthetic_data,
    column_names=['room_rate', 'room_type'],
    table_name='guests',
    metadata=metadata
)

fig.show()

# ---- Cell ----
synthesizer.save('my_synthesizer.pkl')

synthesizer = HMASynthesizer.load('my_synthesizer.pkl')

# ---- Cell ----
custom_synthesizer = HMASynthesizer(
    metadata,
    verbose=False
)

custom_synthesizer.set_table_parameters(
    table_name='hotels',
    table_parameters={
        'default_distribution': 'truncnorm'
    }
)

custom_synthesizer.fit(real_data)

# ---- Cell ----
learned_distributions = custom_synthesizer.get_learned_distributions(table_name='hotels')
learned_distributions['rating']
