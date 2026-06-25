defaultSize = 2
default_stretch = 2
outliers_m = 5.

# Colours
loudness      = "#008b8b"
pitch         = "#e9aad8"
f1            = "#dc143c"
f2            = "#006400"
f3            = "#ffd700"

f1_pitch      = "#7588ff"
f2_pitch      = "#ff8c00"
f3_pitch      = "#9966cc"
weight        = "#c71585"
size          = "#32cd32"


white         = "#88888888"

target_band = "#88888833"

spec = {
    'Loudness': {
        'title': 'Loudness',
        'stretch': 1,
        'mouse_enabled_x': True,
        'mouse_enabled_y': False,
        'y_min': 0,
        'y_max': 1,
        'curves': {
            'Loudness': {
                'size': defaultSize,
                'colour': loudness,
                'analysisResult': 'loudness'
            }
        },
        'targets': {
            'Loudness': {'colour': target_band}
        },
        'linkX': None
    },

    'Pitch': {
        'title': 'Pitch (Hz)',
        'y_min': 0,
        'y_max': 350,
        'stretch': 1,
        'curves': {
            'Pitch': {
                'size': defaultSize,
                'colour': pitch,
                'analysisResult': 'pitch',
            },
            'Pitch_BW': {
                'size': defaultSize,
                'colour': white,
                'analysisResult': 'Pitch_BW',
                'BW': True
            }
        },
        'targets': {
            'Pitch': {'colour': target_band}
        },
        'linkX': 'Loudness'
    },

    "Size": {
        'title': 'Size',
        'y_min': -15,
        'y_max': 25,
        'curves': {
            'Size': {
                'size': defaultSize,
                'colour': size,
                'analysisResult': 'size'
            }
        },
        'targets': {
            'Size': {'colour': target_band}
        },
        'linkX': 'Loudness',
    },

    "Weight": {
        'title': 'Weight',
        'y_min': 0,
        'y_max': 8.0e-7,
        'curves': {
            'Weight': {
                'size': defaultSize,
                'colour': weight,
                'analysisResult': 'weight'
            }
        },
        'targets': {
            'Weight': {'colour': target_band}
        },
        'linkX': 'Loudness',
    },

    'Formants': {
        'title': 'Formants (Hz)',
        'y_min': 0,
        'y_max': 3500,
        'curves': {
            'F1': {
                'size': defaultSize,
                'colour': f1,
                'analysisResult': 'F1'
            },
            'F2': {
                'symbol': 'o',
                'size': defaultSize,
                'colour': f2,
                'analysisResult': 'F2'
            },
            'F3': {
                'size': defaultSize,
                'colour': f3,
                'analysisResult': 'F3'
            },
            'F1 BW': {
                'size': defaultSize,
                'colour': white,
                'analysisResult': 'F1_IBW',
                'BW': True
            },
            'F2 BW': {
                'size': defaultSize,
                'colour': white,
                'analysisResult': 'F2_IBW',
                'BW': True
            },
            'F3 BW': {
                'size': defaultSize,
                'colour': white,
                'analysisResult': 'F3_IBW',
                'BW': True
            }
        },
        'targets': {
            'F1': {'colour': target_band},
            'F2': {'colour': target_band},
            'F3': {'colour': target_band}
        },
        'linkX': 'Loudness'
    },

    'F3/Pitch': {
        'title': 'F3 / Pitch',
        'y_min': 1,
        'y_max': 50,
        'curves': {
            'F3/Pitch': {
                'size': defaultSize,
                'colour': f3_pitch,
                'analysisResult': 'F3_Pitch'
            },
            "F3/Pitch BW": {
                'size': defaultSize,
                'colour': white,
                'analysisResult': 'F3_Pitch_BW',
                'BW': True
            },
        },
        'targets': {
            'F3_Pitch': {'colour': target_band}
        },
        'linkX': 'Loudness'
    },

    'F3_Pitch_rel_amplitude': {
        'title': 'F3 / Pitch rel amp',
        'y_min': -120,
        'y_max': 30,
        'curves': {
            'F3_Pitch_rel_amplitude': {
                'size': defaultSize,
                'colour': f3_pitch,
                'analysisResult': 'F3_Pitch_rel_amplitude'
            },
        },
        'linkX': 'Loudness'
    },

    'F2_Pitch_rel_amplitude': {
        'title': 'F2 / Pitch rel amp',
        'y_min': -120,
        'y_max': 20,
        'curves': {
            'F2_Pitch_rel_amplitude': {
                'size': defaultSize,
                'colour': f2_pitch,
                'analysisResult': 'F2_Pitch_rel_amplitude'
            },
        },
        'linkX': 'Loudness'
    },

    'F1_Pitch_rel_amplitude': {
        'title': 'F1 / Pitch rel amp',
        'y_min': -120,
        'y_max': 20,
        'curves': {
            'F1_Pitch_rel_amplitude': {
                'size': defaultSize,
                'colour': f1_pitch,
                'analysisResult': 'F1_Pitch_rel_amplitude'
            },
        },
        'linkX': 'Loudness'
    },


    'F2/Pitch': {
        'title': 'F2 / Pitch',
        'y_min': 1,
        'y_max': 30,
        'curves': {
            'F2/Pitch': {
                'size': defaultSize,
                'colour': f2_pitch,
                'analysisResult': 'F2_Pitch'
            },
            "F2/Pitch BW": {
                'size': defaultSize,
                'colour': white,
                'analysisResult': 'F2_Pitch_BW',
                'BW': True
            },
        },
        'targets': {
            'F2_Pitch': {'colour': target_band}
        },
        'linkX': 'Loudness'
    },

    'F1/Pitch': {
        'title': 'F1 / Pitch',
        'y_min': 1,
        'y_max': 15,
        'curves': {
            'F1/Pitch': {
                'size': defaultSize,
                'colour': f1_pitch,
                'analysisResult': 'F1_Pitch'
            },
            "F1/Pitch BW": {
                'size': defaultSize,
                'colour': white,
                'analysisResult': 'F1_Pitch_BW',
                'BW': True
            },
        },
        'targets': {
            'F1_Pitch': {'colour': target_band}
        },
        'linkX': 'Loudness'
    },

    "Fullness": {
        'title': 'Fullness',
        'y_min': -15,
        'y_max': 25,
        'curves': {
            'Fullness': {
                'size': defaultSize + 2,
                'colour': white,  # Fallback color
                'analysisResult': 'size', # Y-axis
                'colorSource': 'weight'   # Z-axis (Color)
            }
        },
        'targets': {
            'Size': {'colour': target_band}
        },
        'linkX': 'Loudness',
    },

    'Spectrogram': {
            'title': 'Spectrogram',
            'y_min': 0,
            'y_max': 8000,
            'mouse_enabled_x': True,
            'mouse_enabled_y': True,
            'curves': {
                'Spectrogram': {
                    'analysisResult': 'spectrogram',
                    'is_spectrogram': True,  # The flag our PlotController looks for
                    'colour': 'viridis',
                },
            },
            'linkX': 'Loudness' # Synchronize zooming/panning with the other plots
        },

    "logRelF0_H1_A3_sma3nz": {
        'title': 'logRelF0_H1_A3_sma3nz',
        'y_min': -20,
        'y_max': 50,
        'curves': {
            'logRelF0_H1_A3_sma3nz': {
                'size': defaultSize+1,
                'colour': weight,
                'analysisResult': 'logRelF0_H1_A3_sma3nz'
            }
        },
        'targets': {
            'Weight': {'colour': target_band}
        },
        'linkX': 'Loudness',
    },
}