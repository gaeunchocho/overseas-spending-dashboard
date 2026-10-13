"""Parse paired overseas approval CSVs without retaining card identifiers."""
import csv
import io
import re

import pandas as pd


def number(value):
    text = str(value).strip().replace(',', '').replace('−', '-')
    match = re.fullmatch(r'\(?\s*([+-]?\d+(?:\.\d+)?)\s*(?:원|USD)?\s*\)?', text)
    if not match:
        return float('nan')
    amount = float(match.group(1))
    return -abs(amount) if text.startswith('(') else amount


def load_csv(content):
    for encoding in ('utf-8-sig', 'cp949', 'utf-16'):
        try:
            text = content.decode(encoding)
            break
        except UnicodeError:
            continue
    else:
        raise ValueError('파일 인코딩을 읽을 수 없어요. UTF-8 또는 CP949 CSV를 사용해 주세요.')
    rows = list(csv.reader(io.StringIO(text)))
    records, warnings = [], []
    paired = any(len(r) >= 12 and r[2].strip() == '거래일' and r[4].strip() == '가맹점명' for r in rows[:20])
    if paired:
        consumed = set()
        for i, row in enumerate(rows):
            if len(row) < 12 or not re.fullmatch(r'\d{4}[.\-/]\d{2}[.\-/]\d{2}', row[2].strip()):
                continue
            detail = rows[i + 1] if i + 1 < len(rows) else []
            if len(detail) < 12 or not re.fullmatch(r'\d{2}:\d{2}:\d{2}', detail[2].strip()):
                raise ValueError(f'{i + 1}행 거래에 연결할 업종·국가 행이 없어요.')
            consumed.update((i, i + 1))
            records.append({'거래일': row[2].strip().replace('.', '-').replace('/', '-'), '거래시각': detail[2].strip(), '가맹점명': row[4].strip(), '업종': detail[4].strip() or '미분류', '국가': detail[5].strip() or '미분류', '현지금액': number(row[6]), '통화': row[7].strip(), '원화금액': number(row[9]), '상태': detail[11].strip() or '미확인'})
        for i, row in enumerate(rows):
            if i not in consumed and len(row) >= 12 and re.fullmatch(r'\d{2}:\d{2}:\d{2}', row[2].strip()):
                raise ValueError(f'{i + 1}행의 업종 정보와 연결할 거래가 없어요.')
    else:
        source = pd.read_csv(io.StringIO(text), dtype=str)
        source.columns = source.columns.str.strip()
        required = ['거래일', '가맹점명', '업종', '국가', '원화금액', '상태']
        if not set(required).issubset(source.columns):
            raise ValueError('지원 형식이 아니에요. 해외승인내역 원본 또는 거래일, 가맹점명, 업종, 국가, 원화금액, 상태 열이 있는 CSV를 올려주세요.')
        source = source.fillna('')
        for _, row in source.iterrows():
            record = {key: str(row[key]).strip() for key in required}
            record.update({'원화금액': number(row['원화금액']), '현지금액': number(row.get('현지금액', '')), '통화': row.get('통화', ''), '거래시각': row.get('거래시각', '')})
            records.append(record)
    if not records:
        raise ValueError('분석할 거래를 찾지 못했어요.')
    frame = pd.DataFrame(records)
    frame['거래일'] = pd.to_datetime(frame['거래일'], errors='coerce')
    bad = frame['거래일'].isna() | frame['원화금액'].isna()
    if bad.any():
        raise ValueError(f'{int(bad.sum())}건의 날짜 또는 원화금액을 읽지 못했어요. 누락된 합계를 방지하기 위해 파일을 확인해 주세요.')
    frame['업종'] = frame['업종'].replace('', '미분류')
    frame['국가'] = frame['국가'].replace('', '미분류')
    # User verified that 280 means Czechia in this export (not a generic ISO mapping).
    frame['국가'] = frame['국가'].replace({'280': '체코'})
    frame['취소여부'] = frame['상태'].str.contains('취소', na=False)
    frame['월'] = frame['거래일'].dt.strftime('%Y-%m')
    return frame.sort_values('거래일').reset_index(drop=True), warnings


def summarize(frame, column):
    return frame.groupby(column, as_index=False).agg(원화금액=('원화금액', 'sum'), 건수=('원화금액', 'size')).sort_values('원화금액', ascending=False)


def demo_csv():
    return ('거래일,가맹점명,업종,국가,원화금액,상태\n'
            '2025-05-01,Sample Hotel,숙박,일본,180000,정상\n'
            '2025-05-02,Sample Cafe,음식점,일본,18000,정상\n'
            '2025-05-03,Sample Store,슈퍼마켓,일본,45000,정상\n'
            '2025-06-01,Sample Hotel,숙박,체코,220000,정상\n'
            '2025-06-02,Sample Cafe,음식점,체코,28000,정상\n'
            '2025-06-03,Sample Train,교통,체코,65000,정상\n'
            '2025-06-04,Sample Shop,쇼핑,체코,90000,정상\n'
            '2025-06-04,Sample Shop,쇼핑,체코,90000,취소\n').encode('utf-8-sig')
