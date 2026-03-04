#!/usr/bin/bash
set -mxeuo pipefail
source /etc/os-release

case "${NAME}" in
    Oracle*)
        ORAVER="${VERSION//\.*}"
        ORAUPD="${VERSION//*\.}"
        ;;
    *)
        echo "Unsupported build"
        exit 1
        ;;
esac

dnf install -y oraclelinux-developer-release-el${ORAVER} \
               oracle-epel-release-el${ORAVER}
dnf config-manager --enable ol${ORAVER}_codeready_builder
dnf config-manager --enable ol${ORAVER}_developer
if [ "$ORAVER" -ge 10 ]; then
    dnf config-manager --enable ol${ORAVER}_u${ORAUPD}_developer_EPEL
else
    dnf config-manager --enable ol${ORAVER}_developer_EPEL
fi
dnf upgrade
dnf install -y pyproject-rpm-macros python3-wheel rpm-build
dnf builddep -y yo.spec
rpmbuild --define "_sourcedir $(pwd)" \
    --define "_topdir /tmp/buildrpm" \
    -ba yo.spec
mv /tmp/buildrpm/RPMS/noarch/*.rpm ./
mv /tmp/buildrpm/SRPMS/*.rpm ./
