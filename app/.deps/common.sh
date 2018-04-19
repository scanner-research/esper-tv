alias kc=kubectl
alias kga='kc get all'
alias py=python

function kpod() {
    kc get pod --output=json | jq ".items[] | select(.metadata.labels.app == \"scanner-$1\") | .metadata.name" -r
}

function klog() {
    kc logs ${*:2} po/$(kpod $1)
}

source /root/.cargo/env
