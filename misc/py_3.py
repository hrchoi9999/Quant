# English filename: py_3.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/6일차 기본적 팩터모델의 이해/test.py
# Original filename: test.py

# ---- Cell ----
!pip install opendartreader

# ---- Cell ----
import numpy as np
import pandas as pd
import OpenDartReader

# ---- Cell ----
dart = OpenDartReader("9aebac0ee49b223f60f32c0aa868402bfefa5fe8")

# ---- Cell ----
dart.company('035420')

# ---- Cell ----
url = 'https://github.com/FinanceData/KSIC/raw/master/KSIC_09.csv.gz'

df_ksic = pd.read_csv(url, dtype='str')
df_ksic.head(10)

# ---- Cell ----
df_ksic[df_ksic['Industy_code']=='63120']

# ---- Cell ----

