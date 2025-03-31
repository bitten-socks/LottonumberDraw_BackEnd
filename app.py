from flask import Flask, jsonify, request
from flask_cors import CORS, cross_origin
import requests
from bs4 import BeautifulSoup
import numpy as np
import random
import re
import os
import json

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}}, methods=["GET", "POST", "OPTIONS"])

HISTORICAL_FILE = "historical_data.json"  # 미리 업로드된 백본 JSON 파일

# -----------------------------
# 1) 공통 유틸 함수들
# -----------------------------
def fetch_lotto_probability():
    url = "https://dhlottery.co.kr/gameResult.do?method=statByNumber"
    response = requests.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    
    probability_data = {}
    rows = soup.select("table.tbl_data tbody tr")
    for row in rows:
        columns = row.find_all("td")
        if len(columns) >= 2:
            number = int(columns[0].get_text(strip=True))
            winning_count = float(columns[2].get_text(strip=True))
            probability_data[number] = int(winning_count)
    return probability_data

def fetch_lotto_winningNumber():
    url = "https://dhlottery.co.kr/gameResult.do?method=byWin&wiselog=C_A_1_2"
    response = requests.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    
    current_play = {}
    draw_number = soup.find('h4').get_text(strip=True)
    match = re.search(r'\d+', draw_number)
    if match:
        current_play['draw'] = int(match.group())
    
    winning_number = {}
    number_tags = soup.select('.ball_645')
    winning_numbers = [int(tag.get_text()) for tag in number_tags]
    if len(winning_numbers) >= 6:
        winning_number['numbers'] = winning_numbers[:6]
        winning_number['bonus'] = winning_numbers[6]
    
    return {
        "current_play": current_play,
        "winning_number": winning_number
    }

def calculate_current_round(probability_data):
    total_winning_count = sum(probability_data.values())
    current_round = total_winning_count // 7
    print("현재 로또 회차(추정):", current_round)
    return current_round

def calculate_probabilities(probability_data, current_round):
    probabilities = {}
    for number, count in probability_data.items():
        probabilities[number] = (count / current_round) / 7
    return probabilities

def weighted_random_selection(probabilities, available_numbers, n=6):
    weights = [probabilities[num] for num in available_numbers]
    selected_numbers = np.random.choice(available_numbers, size=n, p=weights/np.sum(weights), replace=False)
    return selected_numbers.tolist()

def random_selection(available_numbers, n=6):
    return random.sample(available_numbers, n)

def inverse_weighted_selection(probabilities, available_numbers, n=6):
    inverse_weights = [1/probabilities[num] if probabilities[num] > 0 else 0 for num in available_numbers]
    selected_numbers = np.random.choice(available_numbers, size=n, p=inverse_weights/np.sum(inverse_weights), replace=False)
    return selected_numbers.tolist()

def get_group_pattern(winning_numbers):
    """
    번호군 패턴을 생성합니다.
    매핑:
      1~10  -> 1
      11~20 -> 2
      21~30 -> 3
      31~40 -> 4
      41~45 -> 5
    예: [1, 11, 20, 31, 32, 33] -> [1, 2, 2, 4, 4, 4]
    """
    pattern = []
    for num in winning_numbers:
        if 1 <= num <= 10:
            pattern.append(1)
        elif 11 <= num <= 20:
            pattern.append(2)
        elif 21 <= num <= 30:
            pattern.append(3)
        elif 31 <= num <= 40:
            pattern.append(4)
        elif 41 <= num <= 45:
            pattern.append(5)
        else:
            pattern.append(0)
    return pattern

# -----------------------------
# 2) 번호 추첨 함수 (기존 그대로)
# -----------------------------
def select_numbers_from_groups(selected_groups, probabilities, method_choice, n=6):
    group_ranges = {
        '[1, 10]': list(range(1, 11)),
        '[11, 20]': list(range(11, 21)),
        '[21, 30]': list(range(21, 31)),
        '[31, 40]': list(range(31, 41)),
        '[41, 45]': list(range(41, 46))
    }

    available_numbers = []
    for group in selected_groups:
        group_str = f"[{group[0]}, {group[1]}]"
        if group_str in group_ranges:
            available_numbers.extend(group_ranges[group_str])
        else:
            print(f"그룹 {group_str}이 group_ranges에 없습니다.")
    print("가능한 번호(available_numbers):", available_numbers)

    mandatory_numbers = []
    for group in selected_groups:
        group_str = f"[{group[0]}, {group[1]}]"
        current_group_numbers = group_ranges.get(group_str, [])
        print(f"{group_str} 그룹 번호:", current_group_numbers)
        
        if method_choice == 1:
            mandatory_numbers.append(weighted_random_selection(probabilities, current_group_numbers, 1)[0])
        elif method_choice == 2:
            mandatory_numbers.append(random_selection(current_group_numbers, 1)[0])
        else:
            mandatory_numbers.append(inverse_weighted_selection(probabilities, current_group_numbers, 1)[0])
    print("필수 포함 번호(mandatory_numbers):", mandatory_numbers)

    chosen_numbers = mandatory_numbers.copy()
    print("초기 선택된 번호(chosen_numbers):", chosen_numbers)

    while len(chosen_numbers) < n:
        remaining_numbers = list(set(available_numbers) - set(chosen_numbers))
        print("남은 번호(remaining_numbers):", remaining_numbers)

        if not remaining_numbers:
            print("남은 번호가 없습니다.")
            break

        print(f"추출 방법(method_choice): {method_choice}")

        needed = n - len(chosen_numbers)
        if method_choice == 1:
            new_numbers = weighted_random_selection(probabilities, remaining_numbers, needed)
        elif method_choice == 2:
            new_numbers = random_selection(remaining_numbers, needed)
        else:
            new_numbers = inverse_weighted_selection(probabilities, remaining_numbers, needed)

        chosen_numbers.extend(new_numbers)
        print("현재 선택된 번호(chosen_numbers):", chosen_numbers)

    return list(set(chosen_numbers))

def fetch_lotto_numbers_by_round(round_num):
    print(f"[DEBUG] fetch_lotto_numbers_by_round({round_num}) 호출됨.")
    url = f"https://www.dhlottery.co.kr/gameResult.do?method=byWin&drwNo={round_num}"
    try:
        response = requests.get(url)
        response.raise_for_status()
    except Exception as e:
        print(f"[ERROR] 회차 {round_num} 데이터 요청 실패: {e}")
        return {}
    soup = BeautifulSoup(response.text, 'html.parser')
    data = {}
    
    draw_info = soup.find('h4')
    if draw_info:
        match = re.search(r'\d+', draw_info.get_text(strip=True))
        if match:
            data['round'] = int(match.group())
    else:
        print(f"[WARN] 회차 정보 없음 (round: {round_num})")
    
    number_tags = soup.select('.ball_645')
    if number_tags:
        try:
            winning_numbers = [int(tag.get_text()) for tag in number_tags]
            if len(winning_numbers) >= 6:
                data['winning_numbers'] = winning_numbers[:6]
                data['bonus'] = winning_numbers[6] if len(winning_numbers) > 6 else None
            else:
                print(f"[WARN] 회차 {round_num} 당첨 번호 부족: {winning_numbers}")
        except Exception as e:
            print(f"[ERROR] 회차 {round_num} 당첨 번호 파싱 실패: {e}")
    else:
        print(f"[WARN] 회차 {round_num} 당첨 번호 요소 없음.")
    
    print(f"[DEBUG] fetch_lotto_numbers_by_round({round_num}) 결과: {data}")
    return data

# -----------------------------
# 3) 증분 업데이트 로직 (백본 JSON 활용)
# -----------------------------
def update_historical_data():
    print("[DEBUG] update_historical_data() 호출됨.")
    if not os.path.exists(HISTORICAL_FILE):
        print("[ERROR] 백본 데이터 파일(historical_data.json)이 없습니다. 먼저 업로드하세요.")
        return []
    
    try:
        with open(HISTORICAL_FILE, "r") as f:
            historical_data = json.load(f)
        print(f"[DEBUG] 캐시 파일에서 {len(historical_data)} 개의 회차 데이터를 로드함.")
    except Exception as e:
        print(f"[ERROR] 캐시 파일 로드 실패: {e}")
        return []
    
    try:
        current_data = fetch_lotto_winningNumber()
        current_round = current_data["current_play"]["draw"]
        print(f"[DEBUG] 현재 회차: {current_round}")
    except Exception as e:
        print(f"[ERROR] 현재 회차 데이터 가져오기 실패: {e}")
        return historical_data
    
    if len(historical_data) == 0:
        max_round = 0
    else:
        max_round = max(item["round"] for item in historical_data)
    
    target_round = current_round - 1  # 발표된 최신 회차
    print(f"[DEBUG] 캐시 최대 회차: {max_round}, 업데이트 대상: {max_round+1} ~ {target_round}")
    
    new_data = []
    for r in range(max_round + 1, target_round + 1):
        try:
            data = fetch_lotto_numbers_by_round(r)
            if "winning_numbers" in data and data["winning_numbers"]:
                new_data.append({
                    "round": r,
                    "winning_numbers": data["winning_numbers"]
                    # "bonus": data.get("bonus")  # 필요시 추가
                })
                print(f"[DEBUG] 회차 {r} -> {data['winning_numbers']}")
            else:
                print(f"[WARN] 회차 {r} 데이터가 없거나 빈 값.")
        except Exception as e:
            print(f"[ERROR] 회차 {r} 업데이트 실패: {e}")
    
    if new_data:
        historical_data.extend(new_data)
        historical_data = sorted(historical_data, key=lambda x: x["round"])
        try:
            with open(HISTORICAL_FILE, "w") as f:
                json.dump(historical_data, f)
            print(f"[DEBUG] {len(new_data)}개 회차 데이터를 캐시에 저장했습니다.")
        except Exception as e:
            print(f"[ERROR] 캐시 파일 저장 실패: {e}")
    else:
        print("[DEBUG] 새로운 회차 데이터가 없습니다.")
    
    return historical_data

# -----------------------------
# 4) 추천 번호 로직 (번호군 패턴 비교)
# -----------------------------
def get_recommended_numbers():
    """
    1) update_historical_data()로 최신 데이터 확보
    2) 최신 회차 당첨 번호의 번호군 패턴을 추출하고,
       과거 회차 중 동일한 번호군 패턴을 가진 회차의 다음 회차 번호군 패턴을 후보로 수집
    3) 후보가 없으면 빈 리스트, 있으면 빈도 순 상위 3개 반환
    """
    print("[DEBUG] get_recommended_numbers() 호출됨.")
    historical_data = update_historical_data()
    if not historical_data:
        raise Exception("역대 당첨 데이터가 없습니다. (캐시 파일이 없거나 로드 실패)")
    
    data_dict = {item['round']: item['winning_numbers'] for item in historical_data}
    
    current_data = fetch_lotto_winningNumber()
    current_round = current_data["current_play"]["draw"]
    previous_round = current_round - 1
    print(f"[DEBUG] 현재 회차: {current_round}, 직전 회차: {previous_round}")

    previous_winning = data_dict.get(previous_round)
    if not previous_winning:
        print(f"[WARN] 캐시에서 직전 회차 {previous_round}가 없음, 개별 조회 시도")
        prev_data = fetch_lotto_numbers_by_round(previous_round)
        previous_winning = prev_data.get("winning_numbers", [])
    
    if not previous_winning:
        raise Exception("직전 회차 당첨번호를 가져올 수 없습니다.")
    
    # 최신(직전) 회차의 번호군 패턴 계산
    previous_pattern = get_group_pattern(previous_winning)
    print(f"[DEBUG] 직전 회차 당첨 번호: {previous_winning} -> 패턴: {previous_pattern}")

    candidate_counts = {}
    for r in data_dict:
        if r < previous_round and (r + 1) in data_dict:
            # 과거 회차 r의 번호군 패턴
            past_pattern = get_group_pattern(data_dict[r])
            if past_pattern == previous_pattern:
                # 후보: (r+1) 회차의 번호군 패턴
                candidate = tuple(get_group_pattern(data_dict[r + 1]))
                candidate_counts[candidate] = candidate_counts.get(candidate, 0) + 1
                print(f"[DEBUG] 회차 {r} (패턴: {past_pattern})와 일치 -> 다음 회차 {r+1}: {get_group_pattern(data_dict[r+1])}")
    
    if not candidate_counts:
        print("[WARN] 일치하는 과거 회차를 찾지 못했습니다. 추천 번호군을 반환할 수 없습니다.")
        return []
    
    sorted_candidates = sorted(candidate_counts.items(), key=lambda x: x[1], reverse=True)
    recommended_candidates = [list(candidate) for candidate, _ in sorted_candidates[:3]]
    print(f"[DEBUG] 최종 추천 번호군: {recommended_candidates}")
    return recommended_candidates

# -----------------------------
# 5) Flask API 라우트
# -----------------------------
@app.route('/api/numbers', methods=['POST', 'OPTIONS'])
def get_numbers():
    if request.method == 'OPTIONS':
        return '', 200
    
    data = request.get_json()
    selected_groups = data.get('selected_groups', [])
    method = data.get('method', 1)
    method_choice = method
    print("선택된 method_choice:", method_choice)
    
    probability_data = fetch_lotto_probability()
    current_round = calculate_current_round(probability_data)
    probabilities = calculate_probabilities(probability_data, current_round)
    
    numbers = select_numbers_from_groups(selected_groups, probabilities, method_choice, n=6)
    numbers.sort()
    print("서버에서 반환하는 번호:", numbers)
    return jsonify({"numbers": numbers})

@app.route('/api/lotto/current', methods=['GET'])
def get_lotto_data():
    try:
        data = fetch_lotto_winningNumber()
        return jsonify({
            'currentRound': data['current_play']['draw'],
            'winningNumbers': data['winning_number']['numbers'],
            'bonusNumber': data['winning_number']['bonus']
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/numbers/recommend', methods=['GET', 'OPTIONS'])
@cross_origin()
def recommend_numbers():
    if request.method == 'OPTIONS':
         return '', 200
    try:
        recommended = get_recommended_numbers()
        return jsonify({"recommended_numbers": recommended})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
# -----------------------------
# 6) QR 등록
# -----------------------------
@app.route('/api/register-lotto', methods=['POST', 'OPTIONS'])
@cross_origin()
def register_lotto():
    if request.method == 'OPTIONS':
        return '', 200

    data = request.get_json()
    url = data.get('url')
    print("[DEBUG] Received URL:", url)
    
    if not url:
        print("[ERROR] URL이 전달되지 않음")
        return jsonify({"error": "URL이 전달되지 않았습니다."}), 400

    # 두 가지 형식을 허용
    expected_prefix1 = "https://m.dhlottery.co.kr/qr.do?method=winQr&v="
    expected_prefix2 = "http://m.dhlottery.co.kr/?v="
    if not (url.startswith(expected_prefix1) or url.startswith(expected_prefix2)):
        print("[ERROR] URL 형식 오류:", url)
        return jsonify({"error": "유효하지 않은 QR 코드입니다."}), 400

    try:
        response = requests.get(url)
        response.raise_for_status()
        print("[DEBUG] 첫 번째 QR 코드 페이지 요청 성공. 응답 길이:", len(response.text))
        print("[DEBUG] Response text snippet:", response.text[:200])
    except Exception as e:
        print("[ERROR] 첫 번째 QR 코드 페이지 요청 실패:", e)
        return jsonify({"error": "QR 코드 페이지를 가져오는데 실패했습니다.", "details": str(e)}), 500

    # 자바스크립트 리다이렉트 코드가 있으면, 새 URL로 재요청
    if "document.location.href" in response.text:
        parts = url.split('?v=')
        if len(parts) == 2:
            param = parts[1]
            from requests.utils import quote
            new_url = "https://m.dhlottery.co.kr/qr.do?method=winQr&v=" + quote(param, safe='')
            print("[DEBUG] 리다이렉트 URL 구성됨:", new_url)
            try:
                response = requests.get(new_url)
                response.raise_for_status()
                print("[DEBUG] 리다이렉트 후 QR 코드 페이지 요청 성공. 응답 길이:", len(response.text))
            except Exception as e:
                print("[ERROR] 리다이렉트 후 QR 코드 페이지 요청 실패:", e)
                return jsonify({"error": "리다이렉트 후 QR 코드 페이지를 가져오는데 실패했습니다.", "details": str(e)}), 500
        else:
            print("[ERROR] URL에서 '?v=' 파라미터 추출 실패")
            return jsonify({"error": "URL에서 '?v=' 파라미터를 추출할 수 없습니다."}), 400

    # HTML 파싱 시작
    soup = BeautifulSoup(response.text, 'html.parser')
    numbers = []

    # 당첨 번호 추출 (상단 번호) - 우선 fallback: 모든 span 태그 검색
    span_elements = soup.find_all('span')
    print("[DEBUG] span 태그 결과 개수 (fallback):", len(span_elements))
    for elem in span_elements:
        text = elem.get_text(strip=True)
        if re.match(r'^\d{1,2}$', text):
            try:
                numbers.append(int(text))
            except ValueError as ve:
                print("[ERROR] 숫자 변환 실패:", ve)
    print("[DEBUG] 추출된 번호 개수 (첫번째 시도):", len(numbers))
    if len(numbers) < 6:
        all_text = soup.get_text()
        print("[DEBUG] 전체 페이지 텍스트 길이:", len(all_text))
        numbers = [int(x) for x in re.findall(r'\b\d{1,2}\b', all_text)]
        numbers = [n for n in numbers if 1 <= n <= 45]
        print("[DEBUG] 추출된 번호 개수 (전체 텍스트 검색 후):", len(numbers))
    if len(numbers) < 6:
        print("[ERROR] 추출된 번호가 부족함:", numbers)
        return jsonify({"error": "로또 번호를 추출할 수 없습니다.", "extracted": numbers}), 400

    winning_numbers = numbers[:6]
    bonus_number = numbers[6] if len(numbers) > 6 else None
    print("[DEBUG] 최종 당첨 번호:", winning_numbers, "보너스 번호:", bonus_number)

    # A~E 행 데이터 추출
    rows_data = []
    # 우선, 모든 <tr> 태그를 순회하여, <th> 태그의 내용이 A~E 중 하나인 행을 찾음
    all_tr = soup.find_all("tr")
    print("[DEBUG] 전체 tr 개수:", len(all_tr))
    for tr in all_tr:
        th = tr.find("th")
        if th:
            label = th.get_text(strip=True)
            if label in ["A", "B", "C", "D", "E"]:
                td = tr.find("td")
                if td:
                    span_list = td.find_all("span")
                    row_numbers = []
                    for span in span_list:
                        text = span.get_text(strip=True)
                        if re.match(r'^\d{1,2}$', text):
                            try:
                                row_numbers.append(int(text))
                            except ValueError as ve:
                                print("[ERROR] 숫자 변환 실패 in row:", ve)
                    rows_data.append({
                        "row": label,
                        "numbers": row_numbers
                    })
    print("[DEBUG] A~E 행 파싱 결과:", rows_data)

    return jsonify({
        "registeredNumbers": winning_numbers,
        "bonus": bonus_number,
        "rowData": rows_data
    })
# -----------------------------
# 7) 메인 실행
# -----------------------------
if __name__ == '__main__':
    app.run(debug=True)