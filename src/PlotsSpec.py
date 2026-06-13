plotPointDefaultSize = 1

outliers_m = 5.

# Colours
loudness      = (0, 255, 255)
pitch         = (255, 0, 255)
ratio_f2_f1   = "#37ff144b"
ratio_f3_f1   = "#ffd9007c"
f1            = "#00bfff6e"
f2            = "#ff7f5073"
f3            = "#ba55d377"
weight        = (220, 20, 60)
weight2       = (220, 20, 60)

spec = {
    'Loudness': {
        'title': 'Loudness',
        'stretch': 1,
        'mouse_enabled_x': True,
        'mouse_enabled_y': False,
        'y_min': 0,
        'y_max': 1,
        'curves': {
            'pitch': {
                'symbol': 'o',
                'symbolSize': plotPointDefaultSize,
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
        'y_min': 0,
        'y_max': 300,
        'curves': {
            'pitch': {
                'symbol': 'o',
                'symbolSize': plotPointDefaultSize,
                'colour': pitch,
                'analysisResult': 'pitch'
            }
        },
        'linkX': 'Loudness'
    },
    'F2_F1_ratio': {
        'title': 'Formant ratio F2/F1',
        'stretch': 2,
        'mouse_enabled_x': True,
        'mouse_enabled_y': True,
        'y_min': 0,
        'y_max': 5,
        'curves': {
            'f1_ratio': {
                'symbol': 'o',
                'symbolSize': plotPointDefaultSize,
                'colour': "#FFFFFF", # ratio_f2_f1,
                'analysisResult': 'F1_ratio'
            },
            "F2_F1_CF_BW": {
                'symbol': 'o',
                'symbolSize': plotPointDefaultSize,
                'colour': ratio_f2_f1,
                'analysisResult': 'F2_F1_IBW',
                'BW': True
            },
        },
        'linkX': 'Loudness'
    },
    'F3_F1_ratio': {
        'title': 'Formant ratio F3/F1',
        'stretch': 2,
        'mouse_enabled_x': True,
        'mouse_enabled_y': True,
        'y_min': 0,
        'y_max': 9,
        'curves': {
            'f3_ratio': {
                'symbol': 'o',
                'symbolSize': plotPointDefaultSize,
                'colour': "#FFFFFF", # ratio_f3_f1,
                'analysisResult': 'F3_ratio'
            },
            "F3_F1_CF_BW": {
                'symbol': 'o',
                'symbolSize': plotPointDefaultSize,
                'colour': ratio_f3_f1,
                'analysisResult': 'F3_F1_IBW',
                'BW': True
            },
        },
        'linkX': 'Loudness'
    },
    'Formants': {
        'title': 'Formants (Hz)',
        'stretch': 2,
        'mouse_enabled_x': True,
        'mouse_enabled_y': True,
        'y_min': 0,
        'y_max': 3500,
        'curves': {
            'F1': {
                'symbol': 'o',
                'symbolSize': plotPointDefaultSize,
                'colour': '#FFFFFF',
                'analysisResult': 'F1'
            },
            'F2': {
                'symbol': 'o',
                'symbolSize': plotPointDefaultSize,
                'colour': '#FFFFFF',
                'analysisResult': 'F2'
            },
            'F3': {
                'symbol': 'o',
                'symbolSize': plotPointDefaultSize,
                'colour': '#FFFFFF',
                'analysisResult': 'F3'
            },
            'F1_IBW': {
                'symbol': 'o',
                'symbolSize': plotPointDefaultSize,
                'colour': f1,
                'analysisResult': 'F1_IBW',
                'BW': True
            },
            'F2_IBW': {
                'symbol': 'o',
                'symbolSize': plotPointDefaultSize,
                'colour': f2,
                'analysisResult': 'F2_IBW',
                'BW': True
            },
            'F3_IBW': {
                'symbol': 'o',
                'symbolSize': plotPointDefaultSize,
                'colour': f3,
                'analysisResult': 'F3_IBW',
                'BW': True
            }
        },
        'linkX': 'Loudness'
    },
    'Weight': {
        'title': 'Weight',
        'stretch': 2,
        'mouse_enabled_x': True,
        'mouse_enabled_y': True,
        'y_min': -0.1,
        'y_max': 0.3,
        'curves': {
            'weight_curve_0_500': {
                'symbol': 'o',
                'symbolSize': plotPointDefaultSize,
                'colour': weight,
                'analysisResult': 'slope_0_500'
            },
            'weight_curve_500_1500': {
                'symbol': 'o',
                'symbolSize': plotPointDefaultSize,
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