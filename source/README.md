# 작업 소스 (도구 · 번역)

록맨 에그제 5 한글 패치를 만드는 데 쓴 빌드·검증 도구와 한국어 번역 파일입니다.
**ROM 은 들어 있지 않습니다.** 빌드하려면 본인이 가진 원본 일본판 ROM(팀 오브 블루스 / 팀 오브 커널)이 필요합니다.

## 구성

| 폴더 | 내용 |
|---|---|
| `tools/` | 빌드·검증 스크립트(Python). 통합 빌드는 `build_dialogue_poc.py`, 번역 검사는 `check_translations.py` |
| `translations/` | 한국어 번역 파일. `story/ko/batch_NNN.txt` 대사·메뉴 번역, `story/batch_NNN.json` 컴파일본, `menu_sources/` 지명·크레딧·게시판 원본표, `glossary.tsv` 용어집 |
| `docs/` | 작업 기록(`HANDOFF.md`)과 작업 폴더 설명서(`WORK_README.md`) |

`translations/story/src/` 는 번역 대조용으로 원문 일본어 줄을 담고 있습니다.

## 그림 글자 도구

| 도구 | 화면 |
|---|---|
| `pet_labels.py` · `sort_labels.py` · `tx_panel.py` · `tab_labels.py` | PET 메인 메뉴, 폴더 정렬 창, 전송 패널, 록맨 상태 탭 |
| `title_menu.py` · `logo_subtitle.py` | 타이틀 메뉴, 로고 부제 |
| `result_labels.py` · `map_labels.py` | 전투 결과 창, 지역 이동 지도 |
| `puzzle_letters.py` | 메인 시스템 전뇌 데이터 블록 퍼즐(한국어 단어 재설계, 블록 글자·아이콘) |

## 빌드에 필요한 것(포함되지 않음)

- 원본 일본판 ROM 두 개(해시는 저장소 첫 화면 README 의 표 참고)
- [TextPet](https://github.com/Prof9/TextPet) 1.0.0 과 EXE5 플러그인(`tools/patch_plugins.py` 가 플러그인을 고쳐 씀)
- 한글 글꼴 [Galmuri](https://github.com/quiple/galmuri) (Galmuri7 / 9 / 11, OFL 1.1)
- 타이틀 로고 부제용 에스코어 드림(S-Core Dream 9)
- 메뉴·이름 칸 글자용 록맨 에그제 1 한국어판 ROM(글리프 추출용)
- 화면 확인용 Mesen 2

경로는 작업 PC 기준으로 적혀 있어 그대로는 돌지 않습니다(`C:\Users\<사용자>\...` 등은 자리표시).
