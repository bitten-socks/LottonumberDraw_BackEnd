from flask import Flask, jsonify, request
from flask_cors import CORS  # CORS 임포트
import requests
from bs4 import BeautifulSoup
import numpy as np
import random
import re
import os
import json

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}}, methods=["GET", "POST", "OPTIONS"])

# -----------------------------
# 1) 전역 설정
# -----------------------------
HISTORICAL_FILE = "historical_data.json"  # 엑셀->JSON 변환 후 업로드된 파일 (백본)

# -----------------------------
# 2) 공통 유틸 함수들
# -----------------------------
def fetch_lotto_probability():
    """
    동행복권 사이트의 번호별 출현 횟수를 크롤링하여 확률 계산에 활용.
    """
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
    """
    동행복권 사이트에서 최신 회차의 당첨 번호(6개 + 보너스)를 가져옴.
    """
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
    """
    동행복권 statByNumber 페이지를 통해 얻은 번호별 출현 횟수 총합으로부터 대략적인 회차를 추정(데모용).
    """
    total_winning_count = sum(probability_data.values())
    current_round = total_winning_count // 7
    print("현재 로또 회차(추정):", current_round)
    return current_round

def calculate_probabilities(probability_data, current_round):
    """
    번호별 출현 횟수를 현재 라운드로 나누어 확률을 계산.
    """
    probabilities = {}
    for number, count in probability_data.items():
        probabilities[number] = (count / current_round) / 7
    return probabilities

def weighted_random_selection(probabilities, available_numbers, n=6):
    """
    번호별 확률에 비례하여 n개 번호를 무작위 선택.
    """
    weights = [probabilities[num] for num in available_numbers]
    selected_numbers = np.random.choice(available_numbers, size=n, p=weights/np.sum(weights), replace=False)
    return selected_numbers.tolist()

def random_selection(available_numbers, n=6):
    """
    단순 랜덤으로 n개 번호 선택.
    """
    return random.sample(available_numbers, n)

def inverse_weighted_selection(probabilities, available_numbers, n=6):
    """
    번호별 확률의 역(1/p)에 비례하여 n개 번호를 무작위 선택.
    """
    inverse_weights = [1/probabilities[num] if probabilities[num] > 0 else 0 for num in available_numbers]
    selected_numbers = np.random.choice(available_numbers, size=n, p=inverse_weights/np.sum(inverse_weights), replace=False)
    return selected_numbers.tolist()

# -----------------------------
# 3) 로또 번호 추첨 로직
# -----------------------------
def select_numbers_from_groups(selected_groups, probabilities, method_choice, n=6):
    """
    특정 번호군(예: [1,10], [11,20] 등)에서 6개 번호를 추출.
    method_choice:
      1 = weighted_random_selection
      2 = random_selection
      3 = inverse_weighted_selection
    """
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

    # 각 그룹에서 최소 1개씩 뽑아오기 (필수 포함 번호)
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

    # 나머지 번호(6개가 될 때까지) 채우기
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
    """
    특정 회차에 대한 당첨 번호(6개 + 보너스)를 개별로 가져오는 함수.
    """
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
# 4) 증분 업데이트 로직
# -----------------------------
def update_historical_data():
    """
    1) 이미 업로드된 historical_data.json을 로드
    2) 캐시에 없는 회차만 개별 크롤링
    3) 캐시에 추가 저장
    """
    print("[DEBUG] update_historical_data() 호출됨.")
    if not os.path.exists(HISTORICAL_FILE):
        # 전체 크롤링 대신, 파일이 없으면 에러 메시지만 출력
        print("[ERROR] 백본 데이터 파일(historical_data.json)이 없습니다. 먼저 업로드하세요.")
        return []
    
    # 1) 캐시 파일 로드
    try:
        with open(HISTORICAL_FILE, "r") as f:
            historical_data = json.load(f)
        # 로그 확인
        print(f"[DEBUG] 캐시 파일에서 {len(historical_data)} 개의 회차 데이터를 로드함.")
    except Exception as e:
        print(f"[ERROR] 캐시 파일 로드 실패: {e}")
        return []
    
    # 2) 최신 회차 파악
    try:
        current_data = fetch_lotto_winningNumber()
        current_round = current_data["current_play"]["draw"]
        print(f"[DEBUG] 현재 회차: {current_round}")
    except Exception as e:
        print(f"[ERROR] 현재 회차 데이터 가져오기 실패: {e}")
        return historical_data
    
    # 3) 캐시에 없는 회차만 업데이트
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
                # 보너스 번호도 저장하려면 item["bonus"]를 추가
                new_data.append({
                    "round": r,
                    "winning_numbers": data["winning_numbers"]
                    # "bonus": data.get("bonus")   # 필요시 추가
                })
                print(f"[DEBUG] 회차 {r} -> {data['winning_numbers']}")
            else:
                print(f"[WARN] 회차 {r} 데이터가 없거나 빈 값.")
        except Exception as e:
            print(f"[ERROR] 회차 {r} 업데이트 실패: {e}")
    
    # 4) 새 데이터가 있으면 파일에 저장
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
# 5) 추천 번호 로직
# -----------------------------
def get_recommended_numbers():
    """
    1) update_historical_data()로 최신 데이터 확보
    2) 직전 회차 당첨번호와 동일한 기록을 가진 과거 회차를 찾아서,
       그 다음 회차의 번호군을 후보로 수집
    3) 상위 3개 후보 반환
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

    # 직전 회차 당첨번호
    previous_winning = data_dict.get(previous_round)
    if not previous_winning:
        print(f"[WARN] 캐시에서 직전 회차 {previous_round}가 없음, 개별 조회 시도")
        prev_data = fetch_lotto_numbers_by_round(previous_round)
        previous_winning = prev_data.get("winning_numbers", [])
    
    if not previous_winning:
        raise Exception("직전 회차 당첨번호를 가져올 수 없습니다.")
    
    print(f"[DEBUG] 직전 회차 당첨 번호: {previous_winning}")

    # 후보 수집: 과거 회차 중, 당첨번호가 previous_winning과 동일한 경우
    candidate_counts = {}
    for r in data_dict:
        if r < previous_round and (r + 1) in data_dict:
            if data_dict[r] == previous_winning:
                next_nums = tuple(data_dict[r + 1])
                candidate_counts[next_nums] = candidate_counts.get(next_nums, 0) + 1
                print(f"[DEBUG] 회차 {r}와 일치 -> 다음 회차 {r+1}: {data_dict[r+1]}")

    if not candidate_counts:
        raise Exception("일치하는 과거 회차를 찾을 수 없습니다.")

    sorted_candidates = sorted(candidate_counts.items(), key=lambda x: x[1], reverse=True)
    recommended_candidates = [list(candidate) for candidate, _ in sorted_candidates[:3]]
    print(f"[DEBUG] 최종 추천 번호군: {recommended_candidates}")
    return recommended_candidates

# -----------------------------
# 6) Flask 라우트 설정
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
    
    # 1. 확률 데이터 가져오기
    probability_data = fetch_lotto_probability()
    current_round = calculate_current_round(probability_data)
    probabilities = calculate_probabilities(probability_data, current_round)
    
    # 2. 번호 추첨
    numbers = select_numbers_from_groups(selected_groups, probabilities, method_choice, n=6)
    numbers.sort()
    print("서버에서 반환하는 번호:", numbers)
    return jsonify({"numbers": numbers})

@app.route('/api/lotto/current', methods=['GET'])
def get_lotto_data():
    """
    최신 회차와 당첨 번호(6개+보너스) 반환
    """
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
def recommend_numbers():
    if request.method == 'OPTIONS':
        return '', 200
    try:
        recommended = get_recommended_numbers()
        return jsonify({"recommended_numbers": recommended})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# -----------------------------
# 7) 메인 실행
# -----------------------------
if __name__ == '__main__':
    app.run(debug=True)
