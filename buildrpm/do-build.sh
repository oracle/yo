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

sudo sh -c 'echo -n "oracle.com" > /etc/dnf/vars/ocidomain'
sudo sh -c 'echo -n "" > /etc/dnf/vars/ociregion'
sudo dnf install -y oraclelinux-developer-release-el${ORAVER} \
                    oracle-epel-release-el${ORAVER}
sudo dnf config-manager --enable ol${ORAVER}_codeready_builder
sudo dnf config-manager --enable ol${ORAVER}_developer
if [ "$ORAVER" -ge 10 ]; then
    sudo dnf config-manager --enable ol${ORAVER}_u${ORAUPD}_developer_EPEL
else
    sudo dnf config-manager --enable ol${ORAVER}_developer_EPEL
fi
sudo dnf upgrade
sudo dnf install -y pyproject-rpm-macros python3-wheel
sudo dnf builddep -y buildrpm/yo.spec
rm -rf buildrmp/tmp
rpmbuild --define "_sourcedir $(pwd)/buildrpm" \
    --define "_topdir $(pwd)/buildrpm/tmp" \
    -ba buildrpm/yo.spec
mv buildrpm/tmp/RPMS/noarch/*.rpm buildrpm/
mv buildrpm/tmp/SRPMS/*.rpm buildrpm/
rm -rf buildrpm/tmp
