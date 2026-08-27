# YouTube Transcript Collector

여러 유튜브 채널의 메타데이터·설명·공개 자막을 동일한 형식으로 보존하는 범용 수집기입니다. 영상과 오디오 파일은 내려받지 않습니다.

## 설치

```bash
cd /설치경로/youtube_transcript_collector
chmod +x run_collect.sh youtube_transcript_collector.py
python3 -m pip install -U yt-dlp
yt-dlp --version
```

## 박종훈의 지식한방 전체 수집

전수 수집은 오래 걸릴 수 있으므로 `tmux` 안에서 포그라운드로 실행하는 방식을 권장합니다.

```bash
cd /설치경로/youtube_transcript_collector

./run_collect.sh \
  --channel-url 'https://www.youtube.com/@kpunch' \
  --source-id kpunch \
  --output-root /저장경로/youtube_sources \
  --sleep-seconds 1.5 \
  --min-free-gb 5
```

같은 명령을 다시 실행하면 `COMPLETED_WITH_SUBTITLE`, `COMPLETED_NO_SUBTITLE`, `FAILED`로 이미 기록된 영상은 건너뜁니다.

실패분만 재시도:

```bash
./run_collect.sh \
  --channel-url 'https://www.youtube.com/@kpunch' \
  --source-id kpunch \
  --output-root /저장경로/youtube_sources \
  --retry-failed
```

자막이 없었던 영상도 나중에 다시 확인:

```bash
./run_collect.sh \
  --channel-url 'https://www.youtube.com/@kpunch' \
  --source-id kpunch \
  --output-root /저장경로/youtube_sources \
  --retry-no-subtitle
```

새 영상 목록을 다시 받아 증분 수집:

```bash
./run_collect.sh \
  --channel-url 'https://www.youtube.com/@kpunch' \
  --source-id kpunch \
  --output-root /저장경로/youtube_sources \
  --refresh-inventory
```

로그인이 필요한 경우에만 브라우저 쿠키를 사용합니다. 쿠키 파일은 결과물에 복사되지 않습니다.

```bash
./run_collect.sh \
  --channel-url 'https://www.youtube.com/@kpunch' \
  --source-id kpunch \
  --output-root /저장경로/youtube_sources \
  --cookies-from-browser firefox
```

## 시험 수집

처음에는 3편만 확인할 수 있습니다.

```bash
./run_collect.sh \
  --channel-url 'https://www.youtube.com/@kpunch' \
  --source-id kpunch-test \
  --output-root /저장경로/youtube_sources \
  --limit 3 \
  --sleep-seconds 0
```

## 결과 구조

```text
youtube_sources/kpunch/
├── source.json
├── inventory.json
├── collection_status.jsonl
├── collection_summary.json
├── video_metadata.jsonl
└── videos/
    └── VIDEO_ID/
        ├── YYYYMMDD_VIDEO_ID.info.json
        ├── YYYYMMDD_VIDEO_ID.description
        └── YYYYMMDD_VIDEO_ID.ko-orig.vtt
```

- `inventory.json`: 해당 수집 시점의 전체 영상 인벤토리
- `collection_status.jsonl`: 영상별 모든 수집 시도 이력
- `collection_summary.json`: 영상별 최신 상태 기준 집계
- `video_metadata.jsonl`: 분석에 필요한 메타데이터 통합본
- `videos/VIDEO_ID`: 원문 추적이 가능한 영상별 자료

`COMPLETED_NO_SUBTITLE`은 실패와 다릅니다. 영상 정보는 확보됐지만 요청한 언어의 공개 자막이 없다는 뜻입니다. 삭제·비공개·연령 제한·네트워크 오류는 `FAILED`로 남습니다.

## 로컬 점검

```bash
cd /설치경로/youtube_transcript_collector
python3 -m py_compile youtube_transcript_collector.py
python3 -m unittest -v test_collector.py
bash -n run_collect.sh
```

## 여러 출처 수집 원칙

- 채널마다 바뀌지 않는 `source-id`를 사용합니다: `chesley`, `ap5798`, `kpunch` 등.
- 출처별 디렉터리를 합치지 않습니다.
- 자동자막과 제작자 자막 파일명을 그대로 보존합니다.
- 분석 단계에서 발언자 본인, 게스트, 기사·보고서 인용을 별도로 구분합니다.
- 자막이 있다는 사실을 발언의 정확성이나 인사이트의 타당성으로 간주하지 않습니다.

## 압축 및 검증

수집 완료 후 영상·오디오 없이 분석 자료만 압축합니다.

```bash
cd /저장경로/youtube_sources
zip -r kpunch_transcripts.zip kpunch \
  -i 'kpunch/*.json' 'kpunch/*.jsonl' 'kpunch/videos/*.vtt' \
     'kpunch/videos/*.description' 'kpunch/videos/*.info.json'

unzip -t kpunch_transcripts.zip
```

저작권과 유튜브 이용약관을 준수하고, 수집 자료는 연구·분석 범위에서 사용해야 합니다.
