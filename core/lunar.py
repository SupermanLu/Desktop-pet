# -*- coding: utf-8 -*-
"""公历 → 农历 转换（1901-2099）。

数据表编码（每项 20 位整数代表一年的农历信息）：
- 第 1~13 位：1~12 月 + 闰月的天数（1=30 天，0=29 天；闰月无则第 13 位无意义）
- 第 16~19 位：闰月编号（0x0F = 该年无闰月）
基准：1901-02-19 = 农历 1901 年正月初一。
"""
from datetime import date

LUNAR_DATA = [
    0xF0EA4, 0xF1D4A, 0x52C94, 0xF0C96, 0xF1536, 0x42AAC, 0xF0AD4, 0xF16B2, 0x22EA4, 0xF0EA4,  # 1901-1910
    0x6364A, 0xF164A, 0xF1496, 0x52956, 0xF055A, 0xF0AD6, 0x216D2, 0xF1B52, 0x73B24, 0xF1D24,  # 1911-1920
    0xF1A4A, 0x5349A, 0xF14AC, 0xF056C, 0x42B6A, 0xF0DA8, 0xF1D52, 0x23D24, 0xF1D24, 0x61A4C,  # 1921-1930
    0xF0A56, 0xF14AE, 0x5256C, 0xF16B4, 0xF0DA8, 0x31D92, 0xF0E92, 0x72D26, 0xF1526, 0xF0A56,  # 1931-1940
    0x614B6, 0xF155A, 0xF0AD4, 0x436AA, 0xF1748, 0xF1692, 0x23526, 0xF152A, 0x72A5A, 0xF0A6C,  # 1941-1950
    0xF155A, 0x52B54, 0xF0B64, 0xF1B4A, 0x33A94, 0xF1A94, 0x8152A, 0xF152E, 0xF0AAC, 0x6156A,  # 1951-1960
    0xF15AA, 0xF0DA4, 0x41D4A, 0xF1D4A, 0xF0C94, 0x3192E, 0xF1536, 0x72AB4, 0xF0AD4, 0xF16D2,  # 1961-1970
    0x52EA4, 0xF16A4, 0xF164A, 0x42C96, 0xF1496, 0x82956, 0xF055A, 0xF0ADA, 0x616D2, 0xF1B52,  # 1971-1980
    0xF1B24, 0x43A4A, 0xF1A4A, 0xA349A, 0xF14AC, 0xF056C, 0x60B6A, 0xF0DAA, 0xF1D92, 0x53D24,  # 1981-1990
    0xF1D24, 0xF1A4C, 0x314AC, 0xF14AE, 0x829AC, 0xF06B4, 0xF0DAA, 0x52D92, 0xF0E92, 0xF0D26,  # 1991-2000
    0x42A56, 0xF0A56, 0xF14B6, 0x22AB4, 0xF0AD4, 0x736AA, 0xF1748, 0xF1692, 0x53526, 0xF152A,  # 2001-2010
    0xF0A5A, 0x4155A, 0xF156A, 0x92B54, 0xF0BA4, 0xF1B4A, 0x63A94, 0xF1A94, 0xF192A, 0x42A5C,  # 2011-2020
    0xF0AAC, 0xF156A, 0x22B64, 0xF0DA4, 0x61D52, 0xF0E4A, 0xF0C96, 0x5192E, 0xF1956, 0xF0AB4,  # 2021-2030
    0x315AC, 0xF16D2, 0xB2EA4, 0xF16A4, 0xF164A, 0x63496, 0xF1496, 0xF0956, 0x50AB6, 0xF0B5A,  # 2031-2040
    0xF16D4, 0x236A4, 0xF1B24, 0x73A4A, 0xF1A4A, 0xF14AA, 0x5295A, 0xF096C, 0xF0B6A, 0x31B54,  # 2041-2050
    0xF1D92, 0x83D24, 0xF1D24, 0xF1A4C, 0x614AC, 0xF14AE, 0xF09AC, 0x40DAA, 0xF0EAA, 0xF0E92,  # 2051-2060
    0x31D26, 0xF0D26, 0x72A56, 0xF0A56, 0xF14B6, 0x52AB4, 0xF0AD4, 0xF16CA, 0x42E94, 0xF1694,  # 2061-2070
    0x8352A, 0xF152A, 0xF0A5A, 0x6155A, 0xF156A, 0xF0B54, 0x4174A, 0xF1B4A, 0xF1A94, 0x3392A,  # 2071-2080
    0xF192C, 0x7329C, 0xF0AAC, 0xF156A, 0x52B64, 0xF0DA4, 0xF1D4A, 0x41C94, 0xF0C96, 0x8192E,  # 2081-2090
    0xF0956, 0xF0AB6, 0x615AC, 0xF16D4, 0xF0EA4, 0x42E4A, 0xF164A, 0xF1516, 0x22936,          # 2091-2099
]

_START_YEAR = 1901
_END_YEAR = 1901 + len(LUNAR_DATA) - 1          # 2099
_SOLAR_START = date(1901, 2, 19)                # 农历 1901 年正月初一
_NO_LEAP = 0x0F


def _leap_month(year: int) -> int:
    """该年闰月编号（0x0F = 无闰月）。"""
    return (LUNAR_DATA[year - _START_YEAR] >> 16) & 0x0F


def _month_days(year: int, month: int) -> int:
    """农历某年某月（1-12）的天数：30 或 29。"""
    return 29 + ((LUNAR_DATA[year - _START_YEAR] >> month) & 0x01)


def _leap_days(year: int) -> int:
    """该年闰月的天数（无闰月返回 0）。"""
    if _leap_month(year) == _NO_LEAP:
        return 0
    return 29 + ((LUNAR_DATA[year - _START_YEAR] >> 13) & 0x01)


def _year_days(year: int) -> int:
    """该农历年总天数（含闰月）。"""
    days = sum(_month_days(year, m) for m in range(1, 13))
    if _leap_month(year) != _NO_LEAP:
        days += _leap_days(year)
    return days


def solar_to_lunar(syear: int, smonth: int, sday: int):
    """公历转农历，返回 (农历年, 农历月, 农历日, 是否闰月)；超出范围返回 None。"""
    offset = (date(syear, smonth, sday) - _SOLAR_START).days
    if offset < 0:
        return None
    lyear = _START_YEAR
    while True:
        yd = _year_days(lyear)
        if offset < yd:
            break
        offset -= yd
        lyear += 1
        if lyear > _END_YEAR:
            return None
    leap = _leap_month(lyear)
    has_leap = leap != _NO_LEAP
    i = 1  # 顺序序号：1..leap 为普通月，leap+1 为闰月，之后为普通月 i-1
    while True:
        if has_leap and i == leap + 1:
            days = _leap_days(lyear)
            if offset < days:
                return (lyear, leap, offset + 1, True)
            offset -= days
            i += 1
            continue
        real_month = i if (not has_leap or i <= leap) else i - 1
        days = _month_days(lyear, real_month)
        if offset < days:
            return (lyear, real_month, offset + 1, False)
        offset -= days
        i += 1
