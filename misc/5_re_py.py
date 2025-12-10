# English filename: 5_re_py.py
# Original path: [능률협회]머신러닝 기반 증권모델링 및 트레이딩 과정 (수강생)/3일차 맞춤형 펀드 설계 및 운용/5. Re_clear.py
# Original filename: 5. Re_clear.py

# ---- Cell ----
import re

# ---- Cell ----
str = '이사원,오대리,구과장,육차장,정부장'

# ---- Cell ----
re.match('이사원', str)     # str이 '이사원'으로 시작되어 인덱스 (0,3)를 반환

# ---- Cell ----
re.match('오대리', str)     # str은 '오대리'로 시작되지 않아 반환값이 없음

# ---- Cell ----
re.search('이사원', str)     # 문자열이 처음 나오는 인덱스 (0,3)을 반환

# ---- Cell ----
re.search('오대리', str)     # 문자열이 처음 나오는 인덱스 (4,7)을 반환

# ---- Cell ----
re.findall('장', str)

# ---- Cell ----
words = re.split(',', str)     # ,을 기준으로 문자열 분리해서 words 리스트에 담기
words

# ---- Cell ----
words[1]

# ---- Cell ----
for w in words:
    if re.search('장', w):     # 장이 들어가는 멤버만 표시
        print(w)

# ---- Cell ----
str = re.sub('구', '9', str)     # '구'를 숫자로 변환
str = re.sub('오', '5', str)     # '오'를 숫자로 변환
str = re.sub('이', '2', str)     # '이'를 숫자로 변환
str = re.sub('육', '6', str)     # '이'를 숫자로 변환
str

# ---- Cell ----
re.findall('0123456789', str)

# ---- Cell ----
re.findall('[0123456789]', str)

# ---- Cell ----
re.findall('[0-9]', str)

# ---- Cell ----
re.findall('0|1|2|3|4|5|6|7|8|9', str)

# ---- Cell ----
re.findall('과장|차장|부장', str)

# ---- Cell ----
re.findall('[과장|차장|부장]', str)

# ---- Cell ----
nums = re.split(',', str)     # ,을 기준으로 문자열 분리해서 nums 리스트에 담기
nums

# ---- Cell ----
for n in nums:
    if re.search('[0-9]', n):     # 숫자가 포함된 직급만 표시
        print(n)

# ---- Cell ----
# 책에는 없지만 실습을 위해 추가한 참고용 코드
for n in nums:
    if re.search(r'\d', n):     # 숫자가 포함된 직급만 표시
        print(n)

# ---- Cell ----
for n in nums:
    if re.search('장', n):     # '장'이 포함된 직급만 표시
        print(n)

# ---- Cell ----
str = ['B', 'BA', 'BAAA', 'BAAAAA', 'CBA', 'CBABA', 'CBABABA']

# ---- Cell ----
for s in str:
    if re.search('BA', s):
        print(s)

# ---- Cell ----
for s in str:
    if re.search('BA..', s):     # BA
        print(s)

# ---- Cell ----
for s in str:
    if re.search('BA...', s):     # BA
        print(s)

# ---- Cell ----
for s in str:
    if re.search('BA*', s):     # B 다음에 A를 0회 이상 반복
        print(s)

# ---- Cell ----
for s in str:
    if re.search('BA+', s):     # B 다음에 A를 1회 이상 반복
        print(s)

# ---- Cell ----
for s in str:
    if re.search('BA{2,3}', s):     # B다음 A를 2회 이상 3회 이하 반복
        print(s)

# ---- Cell ----
for s in str:
    if re.search('BA{3}', s):     # B 다음에 A를 3회 반복
        print(s)

# ---- Cell ----
for s in str:
    if re.search('(BA){3}', s):     # BA를 3회 반복
        print(s)

# ---- Cell ----
for s in str:
    if re.search('BA', s):
        print(s)

# ---- Cell ----
# 문장 시작 기호 ^ 용법
for s in str:
    if re.search('^BA', s):
        print(s)

# ---- Cell ----
for s in str:
    if re.match('BA', s):
        print(s)

# ---- Cell ----
# 문장 끝 기호 $ 용법
for s in str:
    if re.search('BA$', s):
        print(s)

# ---- Cell ----
# 문장 끝 기호 $ 용법
for s in str:
    if re.search('^BA$', s):
        print(s)

# ---- Cell ----
phone = ['010-1111-2222', '01012345678', '010 5555 7777',
         '0709999-0000', '010.2222~5555', '02-3774-3774']
phone_pattern = re.compile(r'010[-~= \.]?[0-9]{4}[-~= \.]?[0-9]{4}')

# ---- Cell ----
for p in phone:
    if phone_pattern.search(p):
        print(p)

# ---- Cell ----
for p in phone:
    if phone_pattern.search(p):
        p = re.sub('[^0-9]', '', p)     # \D 도 같은표현
        print(p[:3] + '-' + p[3:7] + '-' + p[7:])

# ---- Cell ----
str = 'ABcd12!@ 가나'
print('숫자 :', re.findall(r'\d', str))  # 이중 역 슬래시 또는 r 문자열
print('숫자X :', re.findall(r'\D', str))
print('문자 :', re.findall(r'\w', str))
print('문자X :', re.findall(r'\W', str))
print('공백 :', re.findall(r'\s', str))
print('공백X :', re.findall(r'\S', str))

# ---- Cell ----

