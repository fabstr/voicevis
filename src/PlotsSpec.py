defaultSize = 1

outliers_m = 5.

# Colours
loudness      = (0, 255, 255)
pitch         = (255, 0, 255)
ratio_f2_f1   = (57, 255, 20)
ratio_f3_f1   = (255, 215, 0)
f1            = (0, 191, 255)
f2            = (255, 127, 80)
f3            = (186, 85, 211)
weight        = (220, 20, 60)
weight2       = (220, 20, 60)

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
                'colour': loudness,
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
                'colour': pitch,
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
                'colour': ratio_f2_f1,
                'analysisResult': 'F1_ratio'
            },
            'f3_ratio': {
                'symbol': 'o',
                'symbolSize': defaultSize,
                'colour': ratio_f3_f1,
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
                'colour': f1,
                'analysisResult': 'F1'
            },
            'F2': {
                'symbol': 'o',
                'symbolSize': defaultSize,
                'colour': f2,
                'analysisResult': 'F2'
            },
            'F3': {
                'symbol': 'o',
                'symbolSize': defaultSize,
                'colour': f3,
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
                'colour': weight,
                'analysisResult': 'slope_0_500'
            },
            'curve_500_1500': {
                'symbol': 'o',
                'symbolSize': defaultSize,
                'colour': weight2,
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