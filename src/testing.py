"""Compare RAPTOR algorithm outputs between original and parallel versions"""
import json
import os
import argparse
from typing import Dict, List, Set, Any
from pathlib import Path
from collections import defaultdict
import sys

def load_json_file(filepath: str) -> List[Dict]:
    """Load and parse a JSON file"""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON in {filepath}: {e}")
        return []

def normalize_journey(journey: Dict) -> Dict:
    """Normalize a journey dict for consistent comparison"""
    # Create a copy to avoid modifying the original
    normalized = journey.copy()
    
    # Sort any lists that might have different orders but same content
    if 'legs' in normalized and isinstance(normalized['legs'], list):
        # Sort legs by departure time or some consistent key
        try:
            normalized['legs'] = sorted(normalized['legs'], 
                                      key=lambda x: (x.get('departure_time', ''), 
                                                   x.get('route_id', ''),
                                                   x.get('from_stop', '')))
        except (KeyError, TypeError):
            pass  # Keep original order if sorting fails
    
    return normalized

def journey_to_comparable_tuple(journey: Dict) -> tuple:
    """Convert journey to a tuple for set operations and comparison"""
    try:
        # Extract key fields that should be identical between implementations
        departure_time = journey.get('departure_time')
        arrival_time = journey.get('arrival_time')
        total_duration = journey.get('total_duration')
        num_transfers = journey.get('num_transfers', 0)
        
        # Create a tuple of leg information
        legs_info = []
        if 'legs' in journey and isinstance(journey['legs'], list):
            for leg in journey['legs']:
                leg_tuple = (
                    leg.get('route_id'),
                    leg.get('from_stop'),
                    leg.get('to_stop'),
                    leg.get('departure_time'),
                    leg.get('arrival_time')
                )
                legs_info.append(leg_tuple)
        
        return (departure_time, arrival_time, total_duration, num_transfers, tuple(legs_info))
    
    except Exception as e:
        print(f"Warning: Could not create comparable tuple for journey: {e}")
        return (str(journey),)  # Fallback to string representation

def compare_journey_sets(original_journeys: List[Dict], parallel_journeys: List[Dict]) -> Dict:
    """Compare two sets of journeys and return detailed comparison"""
    
    # Convert to sets of comparable tuples
    original_set = {journey_to_comparable_tuple(normalize_journey(j)) for j in original_journeys}
    parallel_set = {journey_to_comparable_tuple(normalize_journey(j)) for j in parallel_journeys}
    
    # Find differences
    only_in_original = original_set - parallel_set
    only_in_parallel = parallel_set - original_set
    common = original_set & parallel_set
    
    return {
        'original_count': len(original_journeys),
        'parallel_count': len(parallel_journeys),
        'original_unique_count': len(original_set),
        'parallel_unique_count': len(parallel_set),
        'common_count': len(common),
        'only_in_original_count': len(only_in_original),
        'only_in_parallel_count': len(only_in_parallel),
        'only_in_original': list(only_in_original)[:5],  # First 5 for brevity
        'only_in_parallel': list(only_in_parallel)[:5],   # First 5 for brevity
        'identical': len(only_in_original) == 0 and len(only_in_parallel) == 0
    }

def compare_directories(original_dir: str, parallel_dir: str, verbose: bool = False) -> Dict:
    """Compare all JSON files between two directories"""
    
    original_path = Path(original_dir)
    parallel_path = Path(parallel_dir)
    
    if not original_path.exists():
        print(f"Error: Original directory {original_dir} does not exist")
        return {}
    
    if not parallel_path.exists():
        print(f"Error: Parallel directory {parallel_dir} does not exist")
        return {}
    
    # Get all JSON files from both directories
    original_files = {f.name for f in original_path.glob('*.json')}
    parallel_files = {f.name for f in parallel_path.glob('*.json')}
    
    all_files = original_files | parallel_files
    missing_in_original = parallel_files - original_files
    missing_in_parallel = original_files - parallel_files
    common_files = original_files & parallel_files
    
    print(f"Found {len(original_files)} files in original directory")
    print(f"Found {len(parallel_files)} files in parallel directory")
    print(f"Common files: {len(common_files)}")
    
    if missing_in_original:
        print(f"Files only in parallel directory: {missing_in_original}")
    if missing_in_parallel:
        print(f"Files only in original directory: {missing_in_parallel}")
    
    comparison_results = {}
    total_differences = 0
    identical_files = 0
    
    print("\n" + "="*80)
    print("DETAILED COMPARISON RESULTS")
    print("="*80)
    
    for filename in sorted(common_files):
        original_file = original_path / filename
        parallel_file = parallel_path / filename
        
        original_journeys = load_json_file(str(original_file))
        parallel_journeys = load_json_file(str(parallel_file))
        
        comparison = compare_journey_sets(original_journeys, parallel_journeys)
        comparison_results[filename] = comparison
        
        if not comparison['identical']:
            total_differences += 1
            print(f"\n📍 {filename}:")
            print(f"   Original: {comparison['original_count']} journeys ({comparison['original_unique_count']} unique)")
            print(f"   Parallel: {comparison['parallel_count']} journeys ({comparison['parallel_unique_count']} unique)")
            print(f"   Common: {comparison['common_count']}")
            print(f"   Only in original: {comparison['only_in_original_count']}")
            print(f"   Only in parallel: {comparison['only_in_parallel_count']}")
            
            if verbose and comparison['only_in_original_count'] > 0:
                print(f"   Sample from only in original: {comparison['only_in_original'][:2]}")
            if verbose and comparison['only_in_parallel_count'] > 0:
                print(f"   Sample from only in parallel: {comparison['only_in_parallel'][:2]}")
        else:
            identical_files += 1
            if verbose:
                print(f"✅ {filename}: IDENTICAL ({comparison['original_count']} journeys)")
    
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Total files compared: {len(common_files)}")
    print(f"Identical files: {identical_files}")
    print(f"Files with differences: {total_differences}")
    
    if total_differences == 0:
        print("🎉 ALL FILES ARE IDENTICAL! The parallel implementation produces the same results.")
    else:
        print(f"⚠️  {total_differences} files have differences. Review the details above.")
        
        # Summary statistics
        total_original_journeys = sum(r['original_count'] for r in comparison_results.values())
        total_parallel_journeys = sum(r['parallel_count'] for r in comparison_results.values())
        total_differences_count = sum(r['only_in_original_count'] + r['only_in_parallel_count'] 
                                    for r in comparison_results.values())
        
        print(f"\nOverall statistics:")
        print(f"  Total original journeys: {total_original_journeys}")
        print(f"  Total parallel journeys: {total_parallel_journeys}")
        print(f"  Total journey differences: {total_differences_count}")
        
        if total_original_journeys > 0:
            difference_percentage = (total_differences_count / total_original_journeys) * 100
            print(f"  Difference rate: {difference_percentage:.2f}%")
    
    return comparison_results

def analyze_differences(comparison_results: Dict, detailed: bool = False):
    """Analyze patterns in the differences"""
    print("\n" + "="*80)
    print("DIFFERENCE ANALYSIS")
    print("="*80)
    
    files_with_extra_in_original = []
    files_with_extra_in_parallel = []
    files_with_both_differences = []
    
    for filename, result in comparison_results.items():
        if not result['identical']:
            only_orig = result['only_in_original_count']
            only_par = result['only_in_parallel_count']
            
            if only_orig > 0 and only_par == 0:
                files_with_extra_in_original.append((filename, only_orig))
            elif only_par > 0 and only_orig == 0:
                files_with_extra_in_parallel.append((filename, only_par))
            elif only_orig > 0 and only_par > 0:
                files_with_both_differences.append((filename, only_orig, only_par))
    
    if files_with_extra_in_original:
        print(f"\nFiles with journeys only in ORIGINAL ({len(files_with_extra_in_original)}):")
        for filename, count in sorted(files_with_extra_in_original, key=lambda x: x[1], reverse=True)[:10]:
            print(f"  {filename}: +{count} journeys")
    
    if files_with_extra_in_parallel:
        print(f"\nFiles with journeys only in PARALLEL ({len(files_with_extra_in_parallel)}):")
        for filename, count in sorted(files_with_extra_in_parallel, key=lambda x: x[1], reverse=True)[:10]:
            print(f"  {filename}: +{count} journeys")
    
    if files_with_both_differences:
        print(f"\nFiles with differences in BOTH directions ({len(files_with_both_differences)}):")
        for filename, orig_count, par_count in sorted(files_with_both_differences, 
                                                     key=lambda x: x[1] + x[2], reverse=True)[:10]:
            print(f"  {filename}: original+{orig_count}, parallel+{par_count}")

def main():
    parser = argparse.ArgumentParser(description="Compare RAPTOR algorithm outputs")
    parser.add_argument(
        "--original-dir", 
        type=str, 
        default="data/output/optimal",
        help="Directory containing original output files"
    )
    parser.add_argument(
        "--parallel-dir", 
        type=str, 
        default="data/output/unknown_optimal",
        help="Directory containing parallel output files"
    )
    parser.add_argument(
        "--verbose", 
        action="store_true",
        help="Show detailed information for each file"
    )
    parser.add_argument(
        "--detailed-analysis", 
        action="store_true",
        help="Show detailed analysis of difference patterns"
    )
    
    args = parser.parse_args()
    
    print("🔍 Comparing RAPTOR algorithm outputs...")
    print(f"Original directory: {args.original_dir}")
    print(f"Parallel directory: {args.parallel_dir}")
    
    comparison_results = compare_directories(
        args.original_dir, 
        args.parallel_dir, 
        args.verbose
    )
    
    if args.detailed_analysis and comparison_results:
        analyze_differences(comparison_results, detailed=True)

if __name__ == "__main__":
    main()