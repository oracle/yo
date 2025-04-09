# Copyright (c) 2025, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/
Name:           yo
Version:        1.9.0
Release:        0%{?dist}
Summary:        A fast and simple CLI client for managing OCI instances

License:        UPL
URL:            https://github.com/oracle/yo
Source:         https://github.com/oracle/yo/archive/refs/tags/v%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3-devel
BuildRequires:  python3dist(sphinx)
BuildRequires:  python3dist(sphinx-argparse)
BuildRequires:  python3dist(pytest)

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
sphinx-build --color -W -bhtml doc %{buildroot}/%{_docdir}/yo


%check
%pytest tests/


%files -n yo -f %{pyproject_files}
%doc %{_docdir}/yo
%doc README.*
%{_bindir}/yo


%changelog
* Wed Apr 9 2025 Stephen Brennan <stephen.s.brennan@oracle.com> - 1.9.0-0
- Initial packaging of 1.9.0
