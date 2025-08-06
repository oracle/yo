# Copyright (c) 2025, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/
Name:           yo
Version:        1.11.0
Release:        0%{?dist}
Summary:        A fast and simple CLI client for managing OCI instances

License:        UPL
URL:            https://github.com/oracle/yo
Source:         https://github.com/oracle/yo/archive/refs/tags/v%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3-devel
BuildRequires:  python3dist(pytest)

# If built with docs, then we need yo's dependencies too
BuildRequires:  python3dist(sphinx)
BuildRequires:  python3dist(sphinx-argparse)
BuildRequires:  python3dist(rich)
BuildRequires:  python3dist(oci)
BuildRequires:  python3dist(argcomplete)

%global _description %{expand:
yo is a command-line client for managing OCI instances. It makes launching OCI
instances as simple as rudely telling your computer "yo, launch an instance".
Its goals are speed, ease of use, and simplicity.
...}

%description %_description

%prep
%autosetup -p1 -n yo-%{version}
echo -n "dnf" >yo/data/pkgman


%build
%pyproject_wheel


%install
%pyproject_install
%pyproject_save_files yo

# If building with docs, be sure to set PYTHONPATH so we auto-generate docs
# based on THIS version of yo, not any installed to the system.
PYTHONPATH=$(pwd) \
    sphinx-build --color -W -bhtml doc %{buildroot}/%{_docdir}/yo
cp README.* %{buildroot}/%{_docdir}/yo/


%check
%pytest tests/


%files -n yo -f %{pyproject_files}
%doc %{_docdir}/yo
%license LICENSE.txt
%license THIRD_PARTY_LICENSES.txt
%{_bindir}/yo


%changelog
* Wed Aug 6 2025 Stephen Brennan <stephen.s.brennan@oracle.com> - 1.11.0-0
- Update to 1.11.0, see documentation for details

* Wed Apr 9 2025 Stephen Brennan <stephen.s.brennan@oracle.com> - 1.10.0-0
- Update to 1.10.0, see documentation for details

* Wed Apr 9 2025 Stephen Brennan <stephen.s.brennan@oracle.com> - 1.9.0-0
- Initial packaging of 1.9.0
