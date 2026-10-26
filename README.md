# 인원관리 프로그램

Python/Tkinter 데스크톱 앱입니다. Google Sheets의 인원 명단을 불러와 1부·2부 세션별 역할 배치와 예약 현황을 관리합니다. 역할 배치에는 부스, 홍보, 상주 인원이 사용됩니다.

## 실행

Windows에서 Python과 pip를 준비한 뒤 소스 폴더에서 실행합니다.

```powershell
cd .\소스코드
py -m pip install -r requirements.txt
py main.py
```

저장소 루트에는 Windows 실행 파일 `main.exe`도 포함되어 있습니다.

## Google Sheets 설정

앱은 Google Sheets API를 사용합니다. 사용 전에 `소스코드/config.py`의 스프레드시트 설정과 서비스 계정 인증 파일 설정을 확인하고, 해당 스프레드시트에 서비스 계정의 접근 권한을 부여해야 합니다. 인증 JSON 파일은 저장소에 커밋하지 마세요.

명단은 `인원명단` 시트에서 읽고 저장합니다. 예약 기능은 `예약` 및 `설정` 시트를 사용하며, 필요한 시트가 없으면 앱에서 생성합니다.

## 파일 구성

- `소스코드/main.py`: Tkinter 앱 시작점과 인원 배치 화면
- `소스코드/reservation.py`: Google Sheets 연동 및 예약 화면
- `소스코드/data_models.py`: 인원과 역할 배치 데이터
- `소스코드/config.py`: 세션·역할·스프레드시트 설정
- `소스코드/requirements.txt`: Python 의존성
