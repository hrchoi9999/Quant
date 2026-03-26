# Redbot Service Profile Guide

## 목적
이 문서는 `stable`, `balanced`, `growth`, `auto` service_profile이 무엇을 의미하는지 정리한다.

## stable
- 성격: 보수형
- 핵심: ETF 방어 sleeve 비중 확대, stock 비중 축소
- 연결 모델:
  - `S6`
  - `Router(stable)`
- 사용자 상품 연결: `안정형`

## balanced
- 성격: 중립형
- 핵심: S2와 S5 중심의 균형 배분
- 연결 모델:
  - `S2`
  - `S5`
  - `Router(balanced)`
- 사용자 상품 연결: `균형형`

## growth
- 성격: 공격형
- 핵심: S3와 S4 중심의 성장형 배분
- 연결 모델:
  - `S3`
  - `S4`
  - `Router(growth)`
- 사용자 상품 연결: `성장형`

## auto
- 성격: 자동전환형
- 핵심: 시장 국면에 따라 내부 모델을 자동 선택
- 연결 모델:
  - `Router(auto)`
- 사용자 상품 연결: `자동전환형`

## 운영 원칙
- service_profile은 사용자 성향과 상품 표현의 번역 레이어다.
- 내부 엔진명을 직접 사용자에게 노출하지 않는다.
- 동일 Router라도 profile에 따라 stock/ETF sleeve bias가 달라질 수 있다.
