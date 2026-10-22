# 이 파일을 scripts\remote.local.psd1 로 복사해서 값을 채우세요 (remote.local.psd1 은 git에 올라가지 않습니다).
@{
    # SSH 접속 대상. ~/.ssh/config 의 별칭(예: wec-compute) 또는 사용자@Tailscale-IP
    Host         = "wec-compute"

    # 계산용 PC의 작업 폴더 (작업마다 하위 폴더가 만들어집니다)
    JobsRoot     = "C:\wec_jobs"

    # 계산용 PC의 python 실행 파일 (PATH에 있으면 python)
    Python       = "python"

    # -Wait 사용 시 상태 확인 간격(초)
    PollSeconds  = 60
}
