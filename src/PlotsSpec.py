spec = {
    'Pitch': {
        'title': 'Pitch (Hz)',
        'stretch': 1,
        'mouse_enabled_x': True,
        'mouse_enabled_y': False,
        'curves': {
            'pitch': {
                'symbol': 'o',
                'symbolSize': 6,
                'symbolBrush': 'c',
                'analysisResult': 'pitch'
            }
        },
        'linkX': None
    },
    'Formant Ratios': {
        'title': 'Formant ratio´s',
        'stretch': 2,
        'mouse_enabled_x': False,
        'mouse_enabled_y': True,
        'curves': {
            'f1_ratio': {
                'symbol': 'o',
                'symbolSize': 6,
                'symbolBrush': 'y',
                'analysisResult': 'F1_ratio'
            },
            'a3_ratio': {
                'symbol': 'o',
                'symbolSize': 6,
                'symbolBrush': 'r',
                'analysisResult': 'A3_ratio'
            }
        },
        'linkX': 'Pitch'
    },
    'Formants': {
        'title': 'Formants (Hz)',
        'stretch': 2,
        'mouse_enabled_x': False,
        'mouse_enabled_y': True,
        'curves': {
            'F1': {
                'symbol': 'o',
                'symbolSize': 5,
                'symbolBrush': 'r',
                'analysisResult': 'F1'
            },
            'F2': {
                'symbol': 'o',
                'symbolSize': 5,
                'symbolBrush': 'g',
                'analysisResult': 'F2'
            },
            'F3': {
                'symbol': 'o',
                'symbolSize': 5,
                'symbolBrush': 'y',
                'analysisResult': 'F3'
            }
        },
        'linkX': 'Pitch'
    },
    'Weight': {
        'title': 'Weight',
        'stretch': 2,
        'mouse_enabled_x': False,
        'mouse_enabled_y': True,
        'curves': {
            'curve_0_500': {
                'symbol': 'o',
                'symbolSize': 5,
                'symbolBrush': 'm',
                'analysisResult': 'slope_0_500'
            },
            'curve_500_1500': {
                'symbol': 'o',
                'symbolSize': 5,
                'symbolBrush': 'w',
                'analysisResult': 'slope_500_1500'
            }
        },
        'linkX': 'Pitch',
        'bottomLabel': {
            'label': 'Time',
            'units': 's'
        }
    }
}