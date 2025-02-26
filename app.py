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

HISTORICAL_FILE = "historical_data.json"  # 증분 업데이트를 위한 데이터 캐시 파일

# 로또 번호 확률 데이터를 가져오는 함수
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

# 현재 회차 및 당첨 번호 데이터를 가져오는 함수
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

# 로또 번호 추첨 라운드 계산 함수
def calculate_current_round(probability_data):
    total_winning_count = sum(probability_data.values())
    current_round = total_winning_count // 7
    print("현재 로또 회차:", current_round)
    return current_round

# 확률 계산 함수
def calculate_probabilities(probability_data, current_round):
    probabilities = {}
    for number, count in probability_data.items():
        probabilities[number] = (count / current_round) / 7
    return probabilities

# 가중치 기반 랜덤 번호 선택 함수
def weighted_random_selection(probabilities, available_numbers, n=6):
    weights = [probabilities[num] for num in available_numbers]
    selected_numbers = np.random.choice(available_numbers, size=n, p=weights/np.sum(weights), replace=False)
    return selected_numbers.tolist()

# 단순 랜덤 번호 선택 함수
def random_selection(available_numbers, n=6):
    return random.sample(available_numbers, n)

# 가중치 역방향 방식 랜덤 번호 선택 함수
def inverse_weighted_selection(probabilities, available_numbers, n=6):
    inverse_weights = [1/probabilities[num] if probabilities[num] > 0 else 0 for num in available_numbers]
    selected_numbers = np.random.choice(available_numbers, size=n, p=inverse_weights/np.sum(inverse_weights), replace=False)
    return selected_numbers.tolist()

# 번호군 그룹을 바탕으로 번호를 선택하는 함수
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

        if method_choice == 1:
            new_numbers = weighted_random_selection(probabilities, remaining_numbers, n - len(chosen_numbers))
        elif method_choice == 2:
            new_numbers = random_selection(remaining_numbers, n - len(chosen_numbers))
        else:
            new_numbers = inverse_weighted_selection(probabilities, remaining_numbers, n - len(chosen_numbers))

        chosen_numbers.extend(new_numbers)
        print("현재 선택된 번호(chosen_numbers):", chosen_numbers)

    return list(set(chosen_numbers))

# 특정 회차의 당첨 번호를 조회하는 함수
def fetch_lotto_numbers_by_round(round_num):
    url = f"https://www.dhlottery.co.kr/gameResult.do?method=byWin&drwNo={round_num}"
    response = requests.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    data = {}
    
    draw_info = soup.find('h4')
    if draw_info:
        match = re.search(r'\d+', draw_info.get_text(strip=True))
        if match:
            data['round'] = int(match.group())
    else:
        print(f"회차 정보를 찾을 수 없습니다. (round: {round_num})")
    
    number_tags = soup.select('.ball_645')
    if number_tags:
        winning_numbers = [int(tag.get_text()) for tag in number_tags]
        if len(winning_numbers) >= 6:
            data['winning_numbers'] = winning_numbers[:6]
            data['bonus'] = winning_numbers[6] if len(winning_numbers) > 6 else None
        else:
            print(f"당첨 번호가 충분하지 않습니다. (round: {round_num})")
    else:
        print(f"당첨 번호 요소를 찾을 수 없습니다. (round: {round_num})")
    
    return data

# 전체 역대 당첨 번호 데이터를 크롤링하는 함수 (최초 실행 시 사용)
def fetch_all_historical_numbers():
    url = "https://www.dhlottery.co.kr/gameResult.do?method=allWin"
    response = requests.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    historical_data = []
    rows = soup.select("table.tbl_data tbody tr")
    for row in rows:
        columns = row.find_all("td")
        if len(columns) >= 7:
            try:
                round_num = int(columns[0].get_text(strip=True))
                numbers = [int(columns[i].get_text(strip=True)) for i in range(1, 7)]
                historical_data.append({
                    "round": round_num,
                    "winning_numbers": numbers
                })
            except Exception as e:
                continue
    return historical_data

# 증분 업데이트 방식: 캐시 파일에 저장된 역대 데이터를 업데이트
def update_historical_data():
    if os.path.exists(HISTORICAL_FILE):
        with open(HISTORICAL_FILE, "r") as f:
            historical_data = json.load(f)
        historical_data = [
            {"round": int(item["round"]), "winning_numbers": item["winning_numbers"]}
            for item in historical_data
        ]
    else:
        historical_data = fetch_all_historical_numbers()
    
    current_data = fetch_lotto_winningNumber()
    current_round = current_data["current_play"]["draw"]
    target_round = current_round - 1  # 최신 당첨 결과가 있는 회차

    if historical_data:
        max_round = max(item["round"] for item in historical_data)
    else:
        max_round = 0

    new_data = []
    for r in range(max_round + 1, target_round + 1):
        try:
            data = fetch_lotto_numbers_by_round(r)
            if "winning_numbers" in data and data["winning_numbers"]:
                new_data.append({
                    "round": r,
                    "winning_numbers": data["winning_numbers"]
                })
        except Exception as e:
            print(f"회차 {r} 업데이트 실패: {e}")

    if new_data:
        historical_data.extend(new_data)
        historical_data = sorted(historical_data, key=lambda x: x["round"])
        with open(HISTORICAL_FILE, "w") as f:
            json.dump(historical_data, f)
        print(f"{len(new_data)}개의 새로운 회차 데이터를 업데이트했습니다.")
    else:
        print("새로운 회차 데이터가 없습니다.")

    return historical_data

# 추천 번호군을 산출하는 함수 (증분 업데이트된 데이터를 사용)
def get_recommended_numbers():
    historical_data = update_historical_data()
    data_dict = {item['round']: item['winning_numbers'] for item in historical_data}
    
    current_data = fetch_lotto_winningNumber()
    current_round = current_data['current_play']['draw']
    previous_round = current_round - 1

    previous_winning = data_dict.get(previous_round)
    if not previous_winning:
        prev_data = fetch_lotto_numbers_by_round(previous_round)
        previous_winning = prev_data.get("winning_numbers", [])
    
    if not previous_winning:
        raise Exception("이전 회차 당첨번호를 가져올 수 없습니다.")
    
    candidate_counts = {}
    for r in data_dict:
        if r < previous_round and (r + 1) in data_dict:
            if data_dict[r] == previous_winning:
                candidate = tuple(data_dict[r + 1])
                candidate_counts[candidate] = candidate_counts.get(candidate, 0) + 1
    
    if not candidate_counts:
        raise Exception("일치하는 과거 회차를 찾을 수 없습니다.")
    
    sorted_candidates = sorted(candidate_counts.items(), key=lambda x: x[1], reverse=True)
    recommended_candidates = [list(candidate) for candidate, count in sorted_candidates[:3]]
    return recommended_candidates

# API 엔드포인트: 번호 생성 (선택된 그룹 및 추출 방식에 따라)
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
    
    if method == 1:
        print("Method 1 선택: select_numbers_from_groups 실행")
        print("selected_groups:", selected_groups)
        print("probabilities:", probabilities)
        numbers = select_numbers_from_groups(selected_groups, probabilities, method_choice, n=6)
        print("추출된 번호:", numbers)
    elif method == 2:
        print("Method 2 선택: random_selection 실행")
        print("selected_groups:", selected_groups)
        numbers = select_numbers_from_groups(selected_groups, probabilities, method_choice, n=6)
        print("추출된 번호:", numbers)
    else:
        print("Method 3 선택: select_numbers_from_groups 실행")
        print("selected_groups:", selected_groups)
        print("probabilities:", probabilities)
        numbers = select_numbers_from_groups(selected_groups, probabilities, method_choice, n=6)
        print("추출된 번호:" , numbers)
    
    numbers.sort()
    print("서버에서 반환하는 번호:", numbers)
    return jsonify({"numbers": numbers})

# API 엔드포인트: 현재 로또 회차 및 당첨 번호 정보
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
def recommend_numbers():
    if request.method == 'OPTIONS':
         return '', 200
    try:
        recommended = get_recommended_numbers()
        return jsonify({"recommended_numbers": recommended})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
