defaultSize = 1

outliers_m = 5.

spec = {
    'Loudness': {
        'title': 'Loudness',
        'stretch': 1,
        'mouse_enabled_x': True,
        'mouse_enabled_y': False,
        'curves': {
            'pitch': {
                'symbol': 'o',
                'symbolSize': defaultSize,
                'symbolBrush': 'w',
                'analysisResult': 'loudness'
            }
        },
        'linkX': None
    },
    'Pitch': {
        'title': 'Pitch (Hz)',
        'stretch': 1,
        'mouse_enabled_x': True,
        'mouse_enabled_y': True,
        'curves': {
            'pitch': {
                'symbol': 'o',
                'symbolSize': defaultSize,
                'symbolBrush': 'c',
                'analysisResult': 'pitch'
            }
        },
        'linkX': 'Loudness'
    },
    'Formant ratios': {
        'title': 'Formant ratios',
        'stretch': 2,
        'mouse_enabled_x': True,
        'mouse_enabled_y': True,
        'curves': {
            'f1_ratio': {
                'symbol': 'o',
                'symbolSize': defaultSize,
                'symbolBrush': 'y',
                'analysisResult': 'F1_ratio'
            },
            'f3_ratio': {
                'symbol': 'o',
                'symbolSize': defaultSize,
                'symbolBrush': 'r',
                'analysisResult': 'F3_ratio'
            }
        },
        'linkX': 'Loudness'
    },
    'Formants': {
        'title': 'Formants (Hz)',
        'stretch': 2,
        'mouse_enabled_x': True,
        'mouse_enabled_y': True,
        'curves': {
            'F1': {
                'symbol': 'o',
                'symbolSize': defaultSize,
                'symbolBrush': 'r',
                'analysisResult': 'F1'
            },
            'F2': {
                'symbol': 'o',
                'symbolSize': defaultSize,
                'symbolBrush': 'g',
                'analysisResult': 'F2'
            },
            'F3': {
                'symbol': 'o',
                'symbolSize': defaultSize,
                'symbolBrush': 'y',
                'analysisResult': 'F3'
            }
        },
        'linkX': 'Loudness'
    },
    'Weight': {
        'title': 'Weight',
        'stretch': 2,
        'mouse_enabled_x': True,
        'mouse_enabled_y': True,
        'curves': {
            'curve_0_500': {
                'symbol': 'o',
                'symbolSize': defaultSize,
                'symbolBrush': 'm',
                'analysisResult': 'slope_0_500'
            },
            'curve_500_1500': {
                'symbol': 'o',
                'symbolSize': defaultSize,
                'symbolBrush': 'w',
                'analysisResult': 'slope_500_1500'
            }
        },
        'linkX': 'Loudness',
        'bottomLabel': {
            'label': 'Time',
            'units': 's'
        }
    }
}