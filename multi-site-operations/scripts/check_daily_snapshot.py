#!/usr/bin/env python3
"""Validate normalized daily GA4 snapshots offline; never fetch, authenticate, or schedule."""
import argparse
from datetime import date, datetime, time, timedelta, timezone
import json
import math
from pathlib import Path
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Timestamps require a timezone')
    return parsed


def unique_strings(values, name):
    if not isinstance(values, list) or not values or any(not isinstance(x, str) or not x.strip() for x in values):
        raise ValueError(name+' must be a nonempty string list')
    if len(set(values)) != len(values):
        raise ValueError('Duplicates in '+name)
    return values


def check(config, snapshots, report_date, now):
    if config.get('schema_version') != 1 or snapshots.get('schema_version') != 1:
        raise ValueError('Unsupported schema version')
    if not config.get('contract_version') or config['contract_version'] != snapshots.get('contract_version'):
        raise ValueError('Snapshot contract version does not match')
    data_mode = snapshots.get('data_mode')
    if data_mode not in ('demo', 'real_snapshot'):
        raise ValueError('Snapshot data_mode must be demo or real_snapshot')
    sites = {}
    for site in config['sites']:
        sid = site['site_id']
        if not isinstance(sid, str) or not sid or sid in sites:
            raise ValueError('Missing or duplicate site_id')
        if not isinstance(site['property_id'], str) or not site['property_id'].isdigit():
            raise ValueError('property_id must be a numeric string, not a measurement ID')
        ZoneInfo(site['timezone'])
        unique_strings(site['hostnames'], 'hostnames')
        unique_strings(site['metrics'], 'metrics')
        if site['dimensions'] != ['date']:
            raise ValueError('This checker requires daily date-only rows')
        for field in ('max_fetch_age_hours', 'settling_hours'):
            value = site[field]
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError(field+' must be positive and finite')
        sites[sid] = site
    if not sites:
        raise ValueError('At least one site is required')
    records, latest = {}, {}
    for row in snapshots['records']:
        sid = row['site_id']
        if sid not in sites:
            raise ValueError('Snapshot references an unknown site: '+str(sid))
        day = date.fromisoformat(row['report_date'])
        key = sid, day
        if key in records:
            raise ValueError('Duplicate site/date row; choose one version explicitly')
        if row['status'] not in ('ok', 'error', 'not_connected'):
            raise ValueError('Unsupported collection status')
        time_field = 'fetched_at' if row['status'] == 'ok' else 'attempted_at'
        fetched = timestamp(row[time_field])
        if fetched > now:
            raise ValueError('Snapshot retrieval/attempt time is in the future')
        if day > fetched.astimezone(ZoneInfo(sites[sid]['timezone'])).date():
            raise ValueError('Snapshot data date is after its fetch date')
        records[key] = row
        if day <= report_date:
            latest[sid] = max(day, latest.get(sid, day))
    results = []
    for sid, site in sites.items():
        tz = ZoneInfo(site['timezone'])
        if report_date > now.astimezone(tz).date():
            raise ValueError('Requested report date is in a site timezone future')
        base = {'site_id': sid, 'report_date': report_date.isoformat(), 'timezone': site['timezone'],
                'values': {metric: None for metric in site['metrics']}, 'flags': []}
        row = records.get((sid, report_date))
        if row is None:
            base.update(status='missing', latest_known_date=latest[sid].isoformat() if sid in latest else None)
            base['flags'].append('no_snapshot_for_requested_date')
            results.append(base)
            continue
        base['method'] = row.get('method')
        if row['status'] != 'ok':
            if not isinstance(row.get('error_reason'), str) or not row['error_reason'].strip():
                raise ValueError('Failed collection requires an error_reason')
            if row.get('values') not in (None, {}):
                raise ValueError('Failed collection must not contain metric values')
            base.update(status='error', collection_status=row['status'], error_reason=row['error_reason'], attempted_at=row['attempted_at'])
            results.append(base)
            continue
        base['fetched_at'] = row['fetched_at']
        if row['method'] not in ('manual_export', 'data_api'):
            raise ValueError('Unknown collection method')
        query = row['query']
        mismatch = []
        for field in ('property_id', 'timezone'):
            if query.get(field) != site[field]:
                mismatch.append(field)
        for field in ('hostnames', 'metrics', 'dimensions'):
            values = unique_strings(query.get(field), 'query.'+field)
            if sorted(values) != sorted(site[field]):
                mismatch.append(field)
        if mismatch:
            base['flags'].append('query_mismatch:'+','.join(mismatch))
        values = row['values']
        if not isinstance(values, dict) or set(values)-set(site['metrics']):
            raise ValueError('Unexpected metric values')
        for metric in site['metrics']:
            value = values.get(metric)
            if value is None:
                base['flags'].append('missing_metric:'+metric)
            elif type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError('Metric values must be finite numbers or null')
            elif metric in ('activeUsers', 'totalUsers', 'sessions', 'screenPageViews') and (value < 0 or int(value) != value):
                raise ValueError('Count metric must be a nonnegative integer')
            elif metric == 'engagementRate' and not 0 <= value <= 1:
                raise ValueError('engagementRate must be between 0 and 1')
            elif not mismatch:
                base['values'][metric] = value
        for field in ('pagination_complete', 'quality_metadata_available'):
            if row.get(field) is not None and type(row[field]) is not bool:
                raise ValueError(field+' must be boolean or null')
        if row.get('pagination_complete') is not True:
            base['flags'].append('pagination_unconfirmed')
        if row.get('quality_metadata_available') is not True:
            base['flags'].append('quality_metadata_unknown')
        else:
            quality = row.get('quality', {})
            for field in ('subjectToThresholding', 'dataLossFromOtherRow'):
                if type(quality.get(field)) is not bool:
                    raise ValueError('Known quality metadata requires boolean '+field)
                if quality[field]:
                    base['flags'].append(field)
            for field in ('samplingMetadatas', 'dataTruncationReasons', 'restrictedMetrics'):
                if not isinstance(quality.get(field), list):
                    raise ValueError('Known quality metadata requires list '+field)
                if quality[field]:
                    base['flags'].append(field)
            if 'emptyReason' not in quality:
                raise ValueError('Known quality metadata requires emptyReason, null when absent')
            if quality['emptyReason']:
                base['flags'].append('empty_report_reason')
        age = (now-timestamp(row['fetched_at'])).total_seconds()/3600
        end = datetime.combine(report_date+timedelta(days=1), time.min, tzinfo=tz)
        elapsed = (now-end.astimezone(timezone.utc)).total_seconds()/3600
        elapsed_at_fetch = (timestamp(row['fetched_at'])-end.astimezone(timezone.utc)).total_seconds()/3600
        stale = age > site['max_fetch_age_hours']
        provisional = elapsed_at_fetch < site['settling_hours']
        if stale:
            base['flags'].append('fetch_too_old')
        if provisional:
            base['flags'].append('fetched_within_processing_window')
            if elapsed >= site['settling_hours']:
                base['flags'].append('refetch_required_after_processing_window')
        quality_limited = any(flag not in ('fetch_too_old', 'fetched_within_processing_window', 'refetch_required_after_processing_window') for flag in base['flags'])
        base['status'] = 'stale' if stale else 'quality_limited' if quality_limited else 'provisional' if provisional else 'ready'
        base.update(fetch_age_hours=round(age, 2), processing_window_elapsed_at_fetch=not provisional,
                    current_processing_window_elapsed=elapsed >= site['settling_hours'])
        results.append(base)
    return {'generated_at': now.isoformat(), 'contract_version': config['contract_version'],
            'data_mode': data_mode,
            'report_date': report_date.isoformat(), 'sites': results,
            'all_ready': all(row['status'] == 'ready' for row in results),
            'cross_site_totals': None, 'measurement_and_business_validity_verified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', type=Path)
    parser.add_argument('snapshots', type=Path)
    parser.add_argument('--report-date', required=True, help='YYYY-MM-DD in each property timezone')
    parser.add_argument('--as-of', help='Timezone-aware ISO timestamp; defaults to now')
    args = parser.parse_args()
    try:
        result = check(json.loads(args.config.read_text(encoding='utf-8')),
                       json.loads(args.snapshots.read_text(encoding='utf-8')),
                       date.fromisoformat(args.report_date),
                       timestamp(args.as_of) if args.as_of else datetime.now(timezone.utc))
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0 if result['all_ready'] else 2
    except (ValueError, KeyError, TypeError, OSError, AttributeError, ZoneInfoNotFoundError) as e:
        print('ERROR: '+str(e), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
